# Context:
1. I need a personal agent capable of a multitude of tasks that will be added later on in development.
2. For now I need an app, UI interface, and the models downloaded.




# Features of the app:
(a)Microphone → (b)Silero VAD → (c)Whisper large-v3-turbo Q4 → (d)Qwen3 4B Instruct → (e)Kokoro-82M with a preset voice → (f)Speakers
This is the pipeline of all the models i need downloaded.
(a): This will just be any input from the computer
(b): This is to determine when i actually start speaking. 
(c): Then, the speech will take my voice and extract text. Do not save the raw recordings, only save the text.
(d): This is the core of the AI. This should reason, and respond
(e): This is to determine the voice output to my speaker.
(e+): Later, I want AI to have capability to run python scripts, search web, etc.
(f): Speakers

# UI layout: 
This is the general idea of what the UI layout should be![[Screenshot 2026-07-14 at 3.17.17 PM.png]]
The sidebar should include all of the functions i will add later. The color scheme is as follows, but make the green less bright. The right section should add all of the chat history
You should be able to select which function you want with your voice.
The UI allows for a more direct aproach, but the main input would still be voice.

