from rest_framework.response import Response

def speak(payload: dict, speech_text: str, http_status: int = 200):
    """
    Einheitliches Antwortschema für Voice+UI.
    Frontend liest `speech_text` für TTS und `data` für UI-Render.
    """
    return Response({"speech_text": speech_text, "data": payload}, status=http_status)
