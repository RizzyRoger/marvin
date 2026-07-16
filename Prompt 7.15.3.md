# Context:
1. Right now I need to collect some responses from marvin and see them to analyse what went well and what needs to be improved
2. Also, some branding changes.
3. There is also a bug where marvin is unable to or unaware of the fact that it can call obsidian functions.
# Features
1. Make the terminal log show marvin's response as well as mine. This is so that I can keep track.
2. Also, make this the app logo
3. ![[b28c1df3-7823-4e4b-8f18-8a8a9c6af0da-removebg-preview.png]]
4. Use the color #C1E1C1 as primary and #cfc6a7 as secondary for design
5. For the problem of calling functions, we need to adress a new pipeline.
6. voice input→Silero→whisper→qwen(a)→kokoro
7. a. qwen should ask itself, "What function does the user ask for?" chat, obsidian etc
8. And then follow through with that.
9. Change the system prompt to better suit this kind of reflective thinking. Also, it is still asking follow up questions.