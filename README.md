# Diplom

Сервис для работы отдела организации практик и стажировок БГТУ "ВОЕНМЕХ".

### Стек

- `FastAPI`
- `SQLAlchemy`
- `Jinja2`
- `MySQL`
- `Redis`

### Запуск через Docker

`.env-default` нужен только как шаблон. Рабочий файл для запуска всегда `.env`.

| Команда | Описание |
|------------|-------------------------------------|
| `cp .env-default .env` | создать локальный `.env` |
| положить дамп в папку `docker-db/` | MySQL импортирует все `*.sql` из этой папки при первом создании пустого volume |
| `docker compose up --build -d` | поднять приложение, MySQL и Redis |
| `docker compose exec app alembic upgrade head` | применить миграции |
| `docker compose exec app python -m src.app.scripts.manage_app_user --username admin --role editor` | создать пользователя `editor` |
| `docker compose exec app python -m src.app.scripts.manage_app_user --username viewer --role viewer` | создать пользователя `viewer` |
| открыть `http://127.0.0.1:8000/login` | открыть страницу входа |

### Повторный импорт дампа в Docker

| Команда | Описание |
|------------|------------------------------------|
| `docker compose down -v` | удалить контейнеры и volume MySQL |
| заменить файлы в `docker-db/` | положить новый дамп |
| `docker compose up --build -d` | заново поднять приложение |
| `docker compose exec app alembic upgrade head` | применить миграции |

### Запуск без Docker

| Команда                                                                               | Описание |
|---------------------------------------------------------------------------------------|----|
| `python3 -m venv .venv`                                                               | создать виртуальное окружение |
| `source .venv/bin/activate`                                                           | активировать окружение |
| `pip install -r requirements.txt`                                                     | установить зависимости |
| `cp .env-default .env`                                                                | создать локальный `.env` |
| проверить в `.env` `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASS`, `REDIS_URL` | настроить локальные MySQL и Redis |
| поместить файл дампа бд в папку docker-db                                             |  |
| `mysql -u root -p < docker-db/tbl.sql`                                                | импортировать дамп в локальную БД |
| `alembic upgrade head`                                                                | применить миграции |
| `python -m src.app.scripts.manage_app_user --username admin --role editor`            | создать пользователя `editor` |
| `python -m src.app.scripts.manage_app_user --username viewer --role viewer`           | создать пользователя `viewer` |
| `fastapi dev src/main.py`                                                             | запустить приложение |

### Запуск Redis

Redis для локального запуска необязателен. Если `REDIS_URL` пустой, приложение работает без кэша логотипов.

| Команда | Описание |
|------------|-------------------------------------|
| `docker run -d --name diplom-redis -p 6379:6379 redis:7-alpine` | запустить Redis в контейнере |
| `docker start diplom-redis` | повторно запустить уже созданный контейнер |
| `docker stop diplom-redis` | остановить Redis |
| `docker rm -f diplom-redis` | удалить контейнер Redis |

Если Redis нужен, в `.env` должно быть:

```env
REDIS_URL=redis://127.0.0.1:6379/0
```

Если Redis не нужен, в `.env` можно оставить:

```env
REDIS_URL=
```

### Создание пользователей

Общий вид команды:

```bash
python -m src.app.scripts.manage_app_user --username <login> --role <editor|viewer> --password <password>
```

| Команда                                                                                  | Описание |
|------------------------------------------------------------------------------------------|-------------------------------------|
| `python -m src.app.scripts.manage_app_user --username admin --role editor --password <password>` | пользователь с правом редактирования |
| `python -m src.app.scripts.manage_app_user --username viewer --role viewer --password <password>`| пользователь только для просмотра |

Если `--password` не передан, скрипт запросит пароль в консоли.

### Миграции

| Команда | Описание |
|------------|-------------------------------------|
| `alembic upgrade head` | применить последнюю миграцию |
| `alembic revision --autogenerate -m "migration_name"` | создать новую миграцию |

### Makefile

| Команда | Описание |
|------------|-------------------------------------|
| `make requirements` | установить зависимости |
| `make start` | поднять контейнеры |
| `make stop` | остановить контейнеры |
| `make isort` | запустить `isort` |
| `make black` | запустить `black` |
| `make format` | запустить `isort` и `black` |
| `make mypy` | запустить `mypy` |
| `make flake8` | запустить `flake8` |
| `make lint` | запустить `mypy` и `flake8` |
| `make test` | запустить тесты |

### Как работает импорт дампа в Docker

`docker compose` сам не ищет дамп на компьютере. Для первого запуска нужно явно положить файл дампа в папку `docker-db/`.

MySQL импортирует этот файл только при создании нового пустого volume. Если volume уже существует, повторного автоимпорта не будет.

Если нужен полностью чистый старт:

| Команда | Описание |
|------------|-------------------------------------|
| `docker compose down -v` | удалить контейнеры и volume MySQL |
| `docker volume ls | grep diplom` | проверить, что старый volume действительно исчез |
| положить актуальный дамп в `docker-db/` | подготовить новый импорт |
| `docker compose up --build -d` | создать новую БД и импортировать дамп заново |
| `docker compose exec app alembic upgrade head` | применить миграции |
