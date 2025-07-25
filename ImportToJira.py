from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI

import requests
import time
import json
import os
import re
from docx import Document
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Доступ к переменным
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

JIRA_URL = os.getenv("JIRA_URL")
EMAIL = os.getenv("EMAIL")
API_TOKEN = os.getenv("API_TOKEN")
JSON_FILE = os.getenv("JSON_FILE")
JIRA_PROJECT_KEY = os.getenv("JIRA_PROJECT_KEY")
TZ_PATH = os.getenv("TZ_PATH")

# ==== Аутентификация ====
auth = (EMAIL, API_TOKEN)
HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json"
}

# === Поддерживаемые типы задач ===
ISSUE_TYPE_MAP = {
    "Эпик": "Эпик",
    "История": "История",
    "Подзадача": "Подзадача"
}

def read_docx_text(path):
    doc = Document(path)
    return '\n'.join([p.text for p in doc.paragraphs if p.text.strip()])

def extract_requirements_from_tz():
    # Загрузка текста из ТЗ
    doc_text = read_docx_text(TZ_PATH)

    # Создаем промпт
    prompt = ChatPromptTemplate.from_messages([
        ("system", "Ты — аналитик, извлекающий требования из ТЗ."),
        ("human", "Вот техническое задание:\n{doc}\n\n"
                  "Извлеки функциональные требования и представь их в виде иерархического списка: "
                  "1. Общие функциональные требования, 2. Функциональные возможности, 3. Пользовательские роли и т.д. "
                  "Вложенность списка максимум до третьего уровня (1.1. 1.1.1.). Чeтвёртый уровень не писать, а переместить в третий."),
    ])

    # Инициализация модели
    model = ChatOpenAI(model="gpt-4o-mini", temperature=0)

    # Цепочка: промпт → модель → парсер
    chain = prompt | model | StrOutputParser()

    # Выполнение
    response = chain.invoke({"doc": doc_text})
    print(response)
    return response

def refine_requirements_to_jira_json(previous_response):
    example_json = f'''{{
      "projects": [
        {{
          "key": "{JIRA_PROJECT_KEY}",
          "issues": [
            {{
              "summary": "1. Общие функциональные требования",
              "issueType": "Эпик",
              "description": "Базовые требования к разработке и функционированию сайта",
              "externalId": "1"
            }},
            {{
              "summary": "1.1. Разработка сайта на современном языке веб-программирования",
              "issueType": "История",
              "description": "Использование современных технологий для разработки сайта",
              "externalId": "2"
            }},
            {{
              "summary": "1.1.1. Минимальное время загрузки и отображения страниц",
              "issueType": "Подзадача",
              "description": "Оптимизация производительности сайта",
              "externalId": "3"
            }}
          ]
        }}
      ]
    }}'''

    prompt = ChatPromptTemplate.from_messages([
        ("system", "Ты — технический аналитик, формирующий задачи для импорта в Jira."),
        ("human",
         "Вот список функциональных требований:\n\n{requirements}\n\n"
         "Преобразуй в JSON Jira по примеру:\n\n{example}"
         "Инструкция:\n"
         "- Используй ключ проекта {key}.\n"
         "- Каждый верхний уровень — это Эпик.\n"
         "- Первый вложенный уровень — История.\n"
         "- Второй вложенный уровень — Подзадача.\n"
         "- Четвёртые уровни включай как описание в родительский пункт.\n"
         "- Поле summary — это название требования.\n"
         "- Поле issueType указывается на русском языке: Эпик, История, Подзадача.\n"
         "- Все элементы в JSON должны иметь уникальный externalId.\n"
         "- Описание (description) заполняй по смыслу, если возможно.\n")
    ])

    model = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    chain = prompt | model | StrOutputParser()

    jira_json_response = chain.invoke({"requirements": previous_response, "example": example_json, "key": JIRA_PROJECT_KEY})
    cleaned = clean_json_response(jira_json_response)
    print(cleaned)

    # Распаковка строки в JSON
    try:
        parsed_json = json.loads(cleaned)
    except json.JSONDecodeError as e:
        print("❌ Ошибка при декодировании JSON:", e)
        return None

        # Сохраняем в файл
    output_path = "issues.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(parsed_json, f, ensure_ascii=False, indent=2)

    print(f"✅ JSON сохранён в файл: {output_path}")

    return cleaned


def clean_json_response(response_text):
    # Удаляем обертки ```json ... ```
    cleaned = re.sub(r"```json\s*([\s\S]*?)\s*```", r"\1", response_text.strip())
    cleaned = cleaned.strip()
    return cleaned


# === Словарь для сопоставления externalId → issueKey (после создания) ===
external_id_to_key = {}
external_id_to_issue = {}

def create_issue(project_key, issue_data, parent_key=None):
    url = f"{JIRA_URL}/rest/api/3/issue"
    issue_type_name = ISSUE_TYPE_MAP[issue_data["issueType"]]

    description_text = issue_data.get("description", "")
    adf_description = {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": description_text
                    }
                ]
            }
        ]
    }

    fields = {
        "project": { "key": project_key },
        "summary": issue_data["summary"],
        "issuetype": { "name": issue_type_name },
        "description": adf_description
    }

    # Добавление родителя для подзадачи
    if issue_type_name == "Подзадача" and parent_key:
        fields["parent"] = { "key": parent_key }

    response = requests.post(url, headers=HEADERS, auth=(EMAIL, API_TOKEN), json={"fields": fields})

    if response.status_code == 201:
        issue_key = response.json()["key"]
        print(f"[✓] Создана задача: {issue_key} — {issue_data['summary']}")
        return issue_key
    else:
        print(f"[✗] Ошибка создания задачи ({issue_data['summary']}): {response.status_code}")
        print(response.text)
        return None

def get_parent_summary(summary):
    # Получаем родительский уровень, например: '1.1.1. ...' → '1.1.'
    parts = summary.strip().split(".")
    if len(parts) >= 3:
        return ".".join(parts[:2]) + "."
    return None

def main():
    reqs = extract_requirements_from_tz()
    refine_requirements_to_jira_json(reqs)

    with open(JSON_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    for project in data["projects"]:
        project_key = project["key"]
        issues = project["issues"]

        # Сохраняем все задачи во временную структуру
        for issue in issues:
            external_id_to_issue[issue["externalId"]] = issue

        # Сначала создаём Эпики и Истории
        for issue in issues:
            if ISSUE_TYPE_MAP[issue["issueType"]] != "Подзадача":
                issue_key = create_issue(project_key, issue)
                if issue_key:
                    external_id_to_key[issue["externalId"]] = issue_key
                time.sleep(0.3)

        # Затем обрабатываем Подзадачи
        for issue in issues:
            if ISSUE_TYPE_MAP[issue["issueType"]] == "Подзадача":
                sub_summary = issue["summary"]
                parent_summary_prefix = get_parent_summary(sub_summary)

                if not parent_summary_prefix:
                    print(f"[!] Невозможно определить родителя для: {sub_summary}")
                    continue

                # Ищем родительскую Историю с подходящим summary
                parent_id = None
                for candidate in issues:
                    if candidate["issueType"] == "История" and candidate["summary"].startswith(parent_summary_prefix):
                        parent_id = candidate["externalId"]
                        break

                if not parent_id or parent_id not in external_id_to_key:
                    print(f"[!] Не найден родитель для подзадачи: {sub_summary}")
                    continue

                parent_key = external_id_to_key[parent_id]
                issue_key = create_issue(project_key, issue, parent_key)
                if issue_key:
                    external_id_to_key[issue["externalId"]] = issue_key
                time.sleep(0.3)

if __name__ == "__main__":
    main()