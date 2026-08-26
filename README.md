# Practice department service

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
| положить дамп в папку `docker-db/` | MySQL импортирует `*.sql` из этой папки при первом создании пустого volume |
| `docker compose up --build -d` | поднять приложение, MySQL и Redis |
| `docker compose exec app alembic upgrade head` | применить миграции |
| `docker compose exec app python -m src.app.scripts.manage_app_user --username admin --role admin` | создать администратора |
| `docker compose exec app python -m src.app.scripts.manage_app_user --username viewer --role viewer` | создать пользователя `viewer` |
| открыть `http://127.0.0.1:8000/login` | открыть страницу входа |

### Повторный импорт дампа в Docker

| Команда | Описание |
|------------|------------------------------------|
| `docker compose down -v` | удалить контейнеры и volume MySQL |
| заменить файл в `docker-db/` | положить новый дамп |
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

Redis для обычного локального запуска необязателен. С Redis доступны очередь, плановая и полная синхронизация; без него доступны только единичные синхронизации с консервативным MySQL limiter-ом.

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
python -m src.app.scripts.manage_app_user --username <login> --role <admin|editor|viewer> --password <password>
```

| Команда                                                                                  | Описание |
|------------------------------------------------------------------------------------------|-------------------------------------|
| `python -m src.app.scripts.manage_app_user --username admin --role editor --password <password>` | пользователь с правом редактирования |
| `python -m src.app.scripts.manage_app_user --username viewer --role viewer --password <password>`| пользователь только для просмотра |
| `python -m src.app.scripts.manage_app_user --username editor --role editor --password <password>`| создание, редактирование и синхронизация одной организации |
| `python -m src.app.scripts.manage_app_user --username administrator --role admin --password <password>`| все права editor и полная синхронизация |

Если `--password` не передан, скрипт запросит пароль в консоли.

### Интеграция Dadata

Интеграция использует официальный метод [«Организация по ИНН или ОГРН»](https://dadata.ru/api/find-party/). API-ключ и секретный ключ хранятся только в локальном `.env` или secret-хранилище:

```env
DADATA_API_KEY=
DADATA_SECRET_KEY=
```

Для `findById/party` отправляется только `DADATA_API_KEY`; секретный ключ сохранен для других методов Dadata и в этот запрос не передается.

Перед первой миграцией с полем `organization.inn` проверьте legacy-дубли: сама миграция остановится с перечнем до 20 ИНН и не создаст unique-ограничение, пока они не исправлены.

Web-приложение ставит lookup и обновления в Redis Streams с consumer group. По умолчанию Docker Compose поднимает два `dadata-worker`; один worker также работает корректно: ручные задачи остаются приоритетнее low-priority задач полного прогона. Очередь, лимиты и расписание сохраняются в Docker volume `redis_data`. При отсутствии Redis lookup и синхронизация одной организации выполняются синхронно с общим MySQL limiter-ом; полная и плановая синхронизация недоступны. При первом запуске worker только фиксирует начало 30-дневного интервала и не запускает массовое обновление.

| Команда | Описание |
|------------|-------------------------------------|
| `docker compose up --build -d` | запустить web-приложение, MySQL, Redis и worker |
| `docker compose stop dadata-worker` | временно остановить обработку Dadata jobs |
| `docker compose start dadata-worker` | возобновить обработку очереди |
| `docker compose run --rm dadata-worker python -m src.app.scripts.dadata_worker --once` | проверить расписание, обработать текущую очередь и завершиться |
| `docker compose logs --tail=100 dadata-worker` | посмотреть статусы worker без вывода ответов Dadata и ключей |

Основные ограничения по умолчанию:

- 25 запросов в секунду при ограничении Dadata 30;
- 20 запросов в секунду для полной синхронизации, чтобы оставить резерв для ручных действий;
- 50 новых соединений в минуту при ограничении Dadata 60;
- 10 000 запросов в сутки, из них 200 резервируются для единичных ручных операций;
- один успешный полный прогон в сутки;
- блокировка полного прогона автоматически истекает через 15 минут, если worker аварийно остановился;
- повторные попытки с backoff для сетевых ошибок, HTTP 429 и 5xx;
- статусы jobs хранятся в Redis 24 часа.

При 3 000 организациях bulk limiter 20 req/s даёт около 150 секунд чистого времени запросов. С учётом очереди, сетевых задержек и MySQL целевой бюджет полного прогона — до 5–7 минут; parent-задача ставит дочерние jobs порциями по 50, поэтому очередь не разрастается до тысяч активных записей.

При ошибках:

- `401/403` — проверить ключ, подтверждение почты и дневной лимит в кабинете Dadata;
- `429` — дождаться автоматической повторной попытки; после исчерпания попыток job получит статус `rate_limited`;
- `5xx` или timeout — job завершится ошибкой после ограниченного количества повторов, ручное заполнение карточки останется доступным;
- ошибка Redis — проверить `REDIS_URL` и состояние сервиса `redis`; без Redis недоступна только полная и плановая синхронизация;
- полный прогон с ошибками не считается успешным и не переносит следующее плановое обновление.

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
