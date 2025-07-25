Автоматизация создания задач в Jira на основе ТЗ с использованием LLM

  📌 Описание

Этот Python-скрипт позволяет извлекать функциональные требования из технического задания (в формате .docx) с помощью модели GPT (через LangChain) и автоматически создавать задачи в Jira через REST API.

  Программа:

  Извлекает требования из технического задания с использованием LLM.

  Преобразует их в структуру, совместимую с Jira (Эпики → Истории → Подзадачи).

  Сохраняет промежуточный JSON-файл (issues.json).

  Автоматически создает задачи в Jira по этой структуре, включая вложенность подзадач.

🚀 Установка и запуск
1.   Клонировать репозиторий

    git clone https://github.com/your-username/your-repo-name.git

    cd your-repo-name

2.   Установить зависимости

    pip install -r requirements.txt
    
4.   Создать .env файл
Создайте файл .env и укажите в нём следующие переменные:

    OPENAI_API_KEY=sk-...
    TAVILY_API_KEY=...
    JIRA_URL=https://your-domain.atlassian.net
    EMAIL=your-email@example.com
    API_TOKEN=your-jira-api-token
    JSON_FILE=issues.json
    JIRA_PROJECT_KEY=...
    TZ_PATH=III. Техническая часть.docx
   
5.   Запуск

    python ImportToJira.py
