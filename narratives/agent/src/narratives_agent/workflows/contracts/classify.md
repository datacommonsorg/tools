<!--
Code-owned contract for the `classify` phase (`workflows/prompt_contracts.py`).
This text is appended after `config.prompts.classify` on every classify
request and cannot be overridden by instance configuration.
-->
The user message that carries the current request opens with a
`Current date: YYYY-MM-DD` line written by the server. Resolve relative
dates against it, and disregard any other statement of the current date in
the question or the conversation.
