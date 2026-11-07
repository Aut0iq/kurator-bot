@echo off
chcp 65001 >nul
rem Загрузка бота на свой Linux-сервер (VDS) и установка / обновление одной командой.
rem Нужен Windows 10/11 (в нём уже есть ssh, scp и tar).
cd /d "%~dp0.."
echo.
echo === Куратор +: загрузка на сервер ===
echo.
set IP=78.17.209.84
set /p IP=IP-адрес сервера [78.17.209.84]: 
set SUSER=root
set /p SUSER=Пользователь SSH [root]: 
set DOMAIN=kyratorvsk.ru
set /p DOMAIN=Домен [kyratorvsk.ru] (впишите - чтобы без домена, bot.%IP%.sslip.io): 
if "%DOMAIN%"=="-" set DOMAIN=
set APK=n
set /p APK=Собрать приложение для Android на сервере? (y/n) [n]: 
set "BUILD="
if /i "%APK%"=="y" set "BUILD= && sudo bash /opt/kurator/android/build_apk.sh"
echo.
echo ВАЖНО: закройте окно run.bat, чтобы бот на этом компьютере остановился.
pause
set FILES=bot webapp deploy android requirements.txt README.md
if exist data set FILES=%FILES% data
if exist .env set FILES=%FILES% .env
if exist .env.example set FILES=%FILES% .env.example
echo.
echo [1/3] Упаковываю файлы...
tar -czf "%TEMP%\kurator.tgz" --exclude=.venv --exclude=__pycache__ --exclude=build --exclude=.gradle %FILES% || goto :fail
echo [2/3] Отправляю на сервер (введите пароль от сервера, если спросит)...
scp "%TEMP%\kurator.tgz" %SUSER%@%IP%:/tmp/kurator.tgz || goto :fail
echo [3/3] Устанавливаю на сервере...
ssh -t %SUSER%@%IP% "rm -rf ~/kurator_src && mkdir -p ~/kurator_src && tar -xzf /tmp/kurator.tgz -C ~/kurator_src && cd ~/kurator_src && if [ -d /opt/kurator ] && [ -z '%DOMAIN%' ]; then sudo bash deploy/update.sh; else sudo bash deploy/install.sh %DOMAIN%; fi%BUILD%" || goto :fail
echo.
echo Готово. Бот работает на сервере — на этом компьютере его запускать больше не нужно.
if /i "%APK%"=="y" echo Приложение для Android: откройте в боте команду /app
pause
goto :eof
:fail
echo.
echo Что-то пошло не так — пришлите скриншот этого окна.
pause
