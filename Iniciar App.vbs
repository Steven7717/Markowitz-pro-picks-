' Arranca Markowitz Pro Picks sin ventana de consola.
'
' Envuelve a "Iniciar App.bat", que sigue siendo quien hace el trabajo. Lo unico
' que decide este fichero es SI esa ventana tiene que verse, y hay tres casos en
' los que si:
'
'   1. Primer arranque. El .bat pregunta dos cosas -- si instalar uv y si crear
'      el acceso directo -- y espera respuesta. Oculto, esas preguntas dejan el
'      proceso colgado para siempre esperando algo que nadie puede contestar.
'   2. Ya hay un servidor vivo. Entonces no se arranca otro: se abre el
'      navegador contra el que existe. Sin esto, cada doble clic dejaria un
'      proceso mas peleandose por el mismo puerto.
'   3. El arranque oculto no llega a levantar el servidor. Ahi se avisa y se
'      reabre con ventana, porque el error solo se puede leer en la consola.
'      Es la red que impide que ocultar la ventana convierta cualquier fallo en
'      "hago doble clic y no pasa nada".
'
' Al arrancar oculto se pone MPP_AUTOAPAGADO: sin ventana que cerrar, el
' programa se apaga solo cuando ya no queda ninguna pestana abierta
' (programa/apagado.py). Si no, cerrar la pestana dejaria el servidor vivo para
' siempre y el arranque siguiente se encontraria el puerto cogido.

Option Explicit

Const PUERTO = "8501"
Const ESPERA_MAX = 120   ' segundos que se le dan al servidor para responder

Dim fso, shell, raiz, bat, marca, i
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

raiz = fso.GetParentFolderName(WScript.ScriptFullName)
bat = """" & raiz & "\Iniciar App.bat" & """"
marca = shell.ExpandEnvironmentStrings("%USERPROFILE%") & "\.markowitz-pro-picks\atajo.txt"

' Recien instalado, uv queda en %USERPROFILE%\.local\bin, que no esta en el PATH.
' Es la misma linea que abre el .bat, y hace falta aqui por lo mismo: sin ella,
' "where uv" no lo encuentra y este guion concluiria que es un primer arranque
' en cada ejecucion.
shell.Environment("PROCESS").Item("PATH") = _
    shell.ExpandEnvironmentStrings("%USERPROFILE%") & "\.local\bin;" & _
    shell.Environment("PROCESS").Item("PATH")

' --- 1. Reutilizar un servidor que ya este vivo -----------------------------
If Vivo() Then
    shell.Run "http://localhost:" & PUERTO, 1, False
    WScript.Quit 0
End If

' --- 2. Primer arranque: con ventana, que hay que contestar cosas -----------
If HayQuePreguntar() Then
    shell.Run bat, 1, False
    WScript.Quit 0
End If

' --- 3. Arranque normal: oculto ---------------------------------------------
With shell.Environment("PROCESS")
    .Item("MPP_SIN_VENTANA") = "1"
    .Item("MPP_AUTOAPAGADO") = "1"
    ' El navegador lo abre este guion, no Streamlit: asi se abre una sola
    ' pestana y solo cuando el servidor ya responde. Con Streamlit abriendolo,
    ' el navegador llega antes que el servidor y ensena un error de conexion.
    .Item("STREAMLIT_SERVER_HEADLESS") = "true"
    .Item("STREAMLIT_SERVER_PORT") = PUERTO
End With
shell.Run bat, 0, False

For i = 1 To ESPERA_MAX
    WScript.Sleep 1000
    If Vivo() Then
        shell.Run "http://localhost:" & PUERTO, 1, False
        WScript.Quit 0
    End If
Next

' --- 4. No ha arrancado: se abre con ventana para poder leer el error -------
shell.Environment("PROCESS").Item("MPP_SIN_VENTANA") = ""
shell.Environment("PROCESS").Item("STREAMLIT_SERVER_HEADLESS") = ""
MsgBox "Markowitz Pro Picks no ha respondido en " & ESPERA_MAX & " segundos." & _
       vbCrLf & vbCrLf & _
       "Se abrira la ventana del lanzador para ver que ha pasado.", _
       vbExclamation, "Markowitz Pro Picks"
shell.Run bat, 1, False


Function Vivo()
    ' Si hay un Streamlit escuchando en el puerto. /_stcore/health devuelve
    ' "ok"; se comprueba el contenido y no solo el codigo 200 para no confundir
    ' a cualquier otro programa que ocupe el mismo puerto con este.
    Dim http
    Vivo = False
    On Error Resume Next
    ' ServerXMLHTTP y no XMLHTTP: es el unico que admite tiempo maximo de
    ' espera. Con el otro, un puerto abierto que no contesta cuelga este guion
    ' indefinidamente y el usuario se queda sin ventana y sin navegador.
    Set http = CreateObject("MSXML2.ServerXMLHTTP.6.0")
    If Err.Number = 0 Then
        http.setTimeouts 2000, 2000, 2000, 2000
        http.Open "GET", "http://localhost:" & PUERTO & "/_stcore/health", False
        http.Send
        If Err.Number = 0 Then
            If http.Status = 200 And InStr(http.responseText, "ok") > 0 Then
                Vivo = True
            End If
        End If
    End If
    Err.Clear
    On Error GoTo 0
End Function


Function HayQuePreguntar()
    ' Tres senales de que el .bat va a querer hablar con alguien. Cualquiera de
    ' ellas basta para mostrar la ventana: equivocarse hacia el lado de
    ' ensenarla cuesta una ventana de mas, y hacia el otro cuesta un proceso
    ' colgado que el usuario no ve ni puede cerrar.
    HayQuePreguntar = True
    If Not fso.FolderExists(raiz & "\programa\.venv") Then Exit Function
    If Not fso.FileExists(marca) Then Exit Function
    If shell.Run("cmd /c where uv", 0, True) <> 0 Then Exit Function
    HayQuePreguntar = False
End Function
