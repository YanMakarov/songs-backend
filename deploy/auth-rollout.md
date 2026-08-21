# Выкат авторизации на прод

Порядок здесь важнее команд. Если сначала включить `required`, уже выложенный
фронт получит 401 на всё и не покажет ничего осмысленного — он про
авторизацию ещё не знает. Если сначала снять Basic auth со статики, публичным
станет всё сразу. Поэтому промежуточный шаг — режим `optional`: API уже умеет
сессии, но никого не отвергает, так что старый фронт продолжает работать, пока
выкладывается новый.

## 1. Бэкенд в режиме `optional`

Появилась зависимость `argon2-cffi`, поэтому переустановка пакета обязательна —
обычный `git pull` её не подтянет.

```bash
cd /srv/apps/songs-backend
sudo -u songs .venv/bin/pip install -e .
```

В `/srv/apps/songs-backend/.env`:

```bash
SONGS_API_AUTH_MODE=optional
SONGS_API_CORS_ORIGINS=https://songs.it-slon.ru
```

`SONGS_API_CORS_ORIGINS` должен точно называть origin фронта. Браузер
отклоняет запрос с куками, если сервер отвечает `*`, и выглядеть это будет не
как 401, а как «все запросы падают на CORS».

```bash
sudo systemctl restart songs-backend
curl -s https://songs-api.it-slon.ru/health
# {"status":"ok","auth":"optional"}
```

## 2. nginx перед API

Проверьте, что в блоке `songs-api.it-slon.ru` есть проброс реального IP —
без него все попытки входа считаются одним клиентом и защита от перебора
перестаёт различать людей:

```nginx
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Real-IP       $remote_addr;
```

Куки при обычном `proxy_pass` проходят сами. Сломать их может только явный
`proxy_hide_header Set-Cookie` или `proxy_set_header Cookie ""` — если такие
строки есть, уберите их.

## 3. Завести пользователя

```bash
cd /srv/apps/songs-backend
sudo -u songs .venv/bin/python -m app.cli user add vasya --display-name "Вася"
sudo -u songs .venv/bin/python -m app.cli user list
```

Пароль спрашивается интерактивно — передавать его аргументом нельзя, он
останется в истории оболочки и будет виден в списке процессов.

## 4. Выложить фронт

```bash
cd frontend && ./deploy/deploy-frontend.sh
```

Новый фронт в режиме `optional` уже требует входа: экран логина показывается
всем, у кого нет сессии. API при этом ещё открыт — это окно закрывается
следующим шагом.

## 5. Закрыть API

```bash
sudo -u songs sed -i 's/^SONGS_API_AUTH_MODE=.*/SONGS_API_AUTH_MODE=required/' \
  /srv/apps/songs-backend/.env
sudo systemctl restart songs-backend
curl -s https://songs-api.it-slon.ru/health
# {"status":"ok","auth":"required"}
```

Проверка, что закрыто:

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://songs-api.it-slon.ru/setlists/setlist1
# 401
curl -s -o /dev/null -w '%{http_code}\n' https://songs-api.it-slon.ru/openapi.json
# 404 — схема в режиме required не публикуется
```

## 6. Снять Basic auth со статики

Только теперь. В блоке `songs.it-slon.ru` удалите (или закомментируйте):

```nginx
auth_basic           "Songs";
auth_basic_user_file /etc/nginx/.htpasswd;
```

```bash
sudo nginx -t && sudo systemctl reload nginx
curl -s -o /dev/null -w '%{http_code}\n' https://songs.it-slon.ru/manifest.webmanifest
# 200 — с этого момента PWA устанавливается нормально
```

Файл `.htpasswd` можно удалить, но спешить некуда — он больше ни на что не
влияет.

## Если что-то пошло не так

Вернуть доступ, не откатывая код:

```bash
sudo -u songs sed -i 's/^SONGS_API_AUTH_MODE=.*/SONGS_API_AUTH_MODE=optional/' \
  /srv/apps/songs-backend/.env
sudo systemctl restart songs-backend
```

`/health` всегда показывает текущий режим, так что «почему прод открыт» —
это один curl, а не заход по ssh.
