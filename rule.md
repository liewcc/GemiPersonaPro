# AI Agent Guidelines

As an AI agent working in this repository, you MUST strictly adhere to the following rules:

## 1. Version Control & GitHub Pushes
- **NEVER** stage, commit, or push any `.json` configuration/data files or `.log` files to GitHub.
- **NEVER** stage, commit, or push the `browser_user_data/` or `browser_session_sandbox/` directories to GitHub, as they contain sensitive profile and session information.
- Always explicitly verify `git status` before committing. If `.json`, `.log`, or sensitive directories are mistakenly tracked or appear in unstaged changes, use `git restore --staged` or `.gitignore` mechanisms to exclude them.
- When tasked with pushing code updates, ONLY push the specific files that were purposefully modified for the current task. Do not execute a blanket `git commit -a` or `git add .` without reviewing the file list carefully. 

## 2. Codebase & UI Language Rules
- **UI Language:** All User Interface elements (including Streamlit labels, buttons, toast messages, output strings, and placeholders) **MUST be written entirely in English**. No Chinese text should exist within the application UI.
- **Code Comments & Docstrings:** All inline code comments, docstrings, and technical documentation within scripts MUST be in English to ensure universal maintainability.

## 3. Conversational Language (Agent-to-User)
- When talking and communicating with the user in the chat/chatbox interface, you must communicate primarily in **Chinese**. 
- It is highly encouraged to seamlessly **mix English terms within the Chinese conversation** when referencing technical terminology, variable names, file paths, or specific UI elements (e.g., "当你点击 'Submit' 按钮时", "这个 `config.json` 里的 `API_KEY` 有问题"). This ensures technical clarity.

## 4. UI Design & Streamlit Patterns
- **Streamlit Component Widths (STRICT MANDATE):**
    - **CRITICAL:** **NEVER** use `use_container_width=True`. It is deprecated and will cause errors.
    - **ALWAYS** use `width='stretch'` for full-width components (e.g., `st.button`, `st.data_editor`, `st.altair_chart`).
    - Failure to follow this is a direct violation of the project's quality standards.
- **Structural Integrity & Atomic Edits:**
    - Before applying any `replace_file_content` or `multi_replace_file_content` calls, you MUST mentally parse the resulting AST.
    - **NEVER** leave unmatched parentheses `)`, brackets `]`, or braces `}`.
    - **NEVER** duplicate entire logic blocks or `elif` statements.
    - If a change is complex, prefer a single `write_to_file` of the entire function or file to guarantee structural correctness.
- **Aesthetics:**
    - Maintain the premium, dark-mode-first aesthetic (glassmorphism, vibrant gradients).
    - Avoid browser default fonts; use the project's design system tokens.
