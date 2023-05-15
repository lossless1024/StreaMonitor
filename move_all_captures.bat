@ECHO OFF
TITLE WAIT !
:: ASSIGN THE FILE PATH OF BATCH FILE TO A VARIABLE
SET "sourceDir=%CD%\downloads"
:: GET THE NAME OF THE FOLDER WHICH THE BATCH FILE IS IN
FOR %%a IN (.) DO SET currentFolder=%%~na
:: GO UP ONE DIRECTORY
::CD ..
:: MAKE A DYNAMIC FOLDER NAME
::SET folderName=Copied From %currentFolder%
SET "folderName=videos"
:: CREATE A FOLDER TO PUT THE COPIED FILES IN
:: IF FOLDER ALREADY EXISTS DELETE IT
IF NOT EXIST "%folderName%" MKDIR "%folderName%"
:: ASSIGN DESTINATION FOLDER TO A VARIABLE
SET "destinationFolder=%CD%\%folderName%"
:: CREATE A LOG FILE IN DESTINATION FOLDER
SET "_report=%destinationFolder%\logxcopy.txt"
:: CREATE ERROR MESSAGE
IF NOT EXIST "%sourceDir%" (ECHO.Could not find %sourceDir% &GoTo:DONE)
:: OVERWRITE PREVIOUS LOG
>"%_report%" (
echo.%date% – %time%
echo.—————————————————
echo.
)
:: COPY FILES
FOR /F "Delims=" %%! IN ('DIR "%sourceDir%\" /b /s /a-d 2^>NUL') DO (
@ECHO.%%! &(
@MOVE /Y "%%!" "%destinationFolder%\")
)
python .\delete_less.py -p "./videos/"
timeout 5 > NUL
python .\chopper.py
:DONE
TITLE,Done...
echo Done!
ECHO.&PAUSE>NUL