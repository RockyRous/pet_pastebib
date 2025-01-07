
### **Сборка образов**

1. **Собрать контейнер на фоне (через Docker Compose):**
   ```bash
   docker compose build
   ```

2. **Собрать только один сервис:**
   ```bash
   docker compose build <service_name>
   # Например:
   docker compose build api
   ```

3. **Собрать образ вручную (без Docker Compose):**
   ```bash
   docker build -t <image_name> <context_path>
   # Например:
   docker build -t pastebin_api ./api
   ```

---

### **Запуск контейнеров**

4. **Запустить все контейнеры на фоне (через Docker Compose):**
   ```bash
   docker compose up -d
   ```

5. **Запустить только один сервис:**
   ```bash
   docker compose up -d <service_name>
   # Например:
   docker compose up -d api
   ```

6. **Запуск контейнеров не на фоне (для вывода логов):**
   ```bash
   docker compose up
   ```

7. **Запуск контейнера вручную (без Compose):**
   ```bash
   docker run -d --name <container_name> <image_name>
   # Например:
   docker run -d --name pastebin_api pastebin_api
   ```

8. **Открыть шелл внутри контейнера:**
   ```bash
   docker exec -it <container_name> /bin/sh
   # Если установлен bash:
   docker exec -it <container_name> /bin/bash
   ```

---

### **Остановка и удаление контейнеров**

9. **Остановить все контейнеры:**
   ```bash
   docker compose down
   ```

10. **Остановить один контейнер:**
    ```bash
    docker stop <container_name>
    # Например:
    docker stop pastebin_api
    ```

11. **Удалить один контейнер:**
    ```bash
    docker rm <container_name>
    # Например:
    docker rm pastebin_api
    ```

12. **Удалить все остановленные контейнеры:**
    ```bash
    docker container prune
    ```

---

### **Работа с логами**

13. **Просмотр логов всех контейнеров:**
    ```bash
    docker compose logs
    ```

14. **Просмотр логов одного сервиса:**
    ```bash
    docker compose logs <service_name>
    # Например:
    docker compose logs api
    ```

15. **Просмотр логов контейнера в реальном времени:**
    ```bash
    docker logs -f <container_name>
    # Например:
    docker logs -f pastebin_api
    ```

---

### **Полезные команды**

16. **Проверить статус всех контейнеров:**
    ```bash
    docker ps -a
    ```

17. **Посмотреть все образы:**
    ```bash
    docker images
    ```

18. **Удалить образ:**
    ```bash
    docker rmi <image_name>
    # Например:
    docker rmi pastebin_api
    ```

19. **Удалить все неиспользуемые образы:**
    ```bash
    docker image prune
    ```

20. **Проверить детали контейнера:**
    ```bash
    docker inspect <container_name>
    ```

21. **Проверить детали образа:**
    ```bash
    docker inspect <image_name>
    ```
