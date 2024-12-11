### Чтобы посмотреть содержимое баз данных PostgreSQL в запущенных контейнерах, можно использовать `psql` — консольный клиент PostgreSQL. Вот пошаговая инструкция с командами:

---

### Шаг 1: Получите доступ к контейнеру

Подключитесь к контейнеру PostgreSQL с помощью команды `docker exec`. Например:

#### Для базы `postgres-hash`:
```bash
docker exec -it postgres_hash sh
```

#### Для базы `postgres-text`:
```bash
docker exec -it postgres_text sh
```

---

### Шаг 2: Подключитесь к PostgreSQL внутри контейнера

В контейнере выполните команду для запуска `psql`:

#### Для базы `pastebin_hash`:
```bash
psql -U user -d pastebin_hash
```

#### Для базы `pastebin_text`:
```bash
psql -U user -d pastebin_text
```

---

### Шаг 3: Выполните команды в `psql`

После подключения вы можете выполнять SQL-запросы для просмотра данных:

#### Посмотреть список таблиц:
```sql
\dt
```

#### Посмотреть содержимое таблицы:
```sql
SELECT * FROM table_name;
```

#### Выйти из `psql`:
```bash
\q
```
