1. Add  own voice recog
2. add noise to know when speaking
3. Tweak startup
# Context:
- With the last version of the app, many issues have appeared
- most notably it cant distinguish only **my** voice meaning that it is hard to complete a prompt withought background talking extending the duration
- Aditionally, it is hard to tell when the ai is done 
# Features
- Use the **SpeechBrain ECAPA-TDNN speaker-verification model** to create a voice profile from several recordings of me, then compare each detected speech segment against that profile and only send matching audio to Whisper; add **pyannote diarization** only when I need to separate multiple speakers in longer conversations.
- Ask for voice recordings and tell me how to do them
- Aditionally, add a notification sound effect for when marvin is listening and when it is not
- Put it into the system prompt that qwen should not output emoji's, personal preference, adn when it gets translated into voice it just says the unicode.
- Aditionally, make the voice the brittish male.

Any clarifications needed, just ask.
More importaintly, if anything breaks, examine 4-7 possible causes, narrow down on 3, and solve them systematically.