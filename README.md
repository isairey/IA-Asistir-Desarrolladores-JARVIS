# J.A.R.V.I.S. - AI Code Assistant

J.A.R.V.I.S. is an intelligent coding assistant that leverages multiple state-of-the-art language models to help you with code generation, modifications, and technical discussions.

![J.A.R.V.I.S.](<public/jarvis.png>)

## Features

- **Integrated Terminal**:
  - Cross-platform terminal support (Windows and Linux)
  - Automatic workspace directory initialization
  - Full xterm.js integration
  - Real-time output streaming
  - Command history support
  - Proper directory tracking
  - Native shell integration (cmd.exe on Windows, bash on Linux)

- **Multi-Model Support**: Choose between different AI models for your coding needs:
  - DeepSeek R1
  - DeepSeek V3
  - Codestral
  - Gemini 2.0 Flash Experimental
  - Grok 2
  - Claude 3.5 Sonnet
  - GPT-4 Turbo
  - GPT-4o Mini
  - GPT-4o
  - o1-mini
  - o1-preview

- **File Attachment Support**:
  - PDF files with text extraction
  - Microsoft Word documents (.docx)
  - Excel spreadsheets with sheet parsing
  - Images with OCR capabilities
  - Enhanced Markdown with GFM support
  - All major programming languages
  - Configuration files
  - Text and documentation files
  - File preview with syntax highlighting
  - Multiple file upload support
  - Progress indicators and file size display
  - Type-specific icons and preview buttons

- **Real-Time Updates**:
  - WebSocket-based notifications
  - Instant feedback for code changes
  - Real-time workspace updates
  - Automatic change notifications

- **Workspace Management**:
  - Create and manage multiple workspaces
  - View workspace history
  - Delete workspaces when no longer needed
  - Rename workspaces
  - Browse workspace file structure

- **Code Generation & Modification**:
  - Generate new code based on natural language prompts
  - Modify existing code with AI assistance
  - Preview changes before applying them
  - View diffs of proposed changes

- **Interactive Chat**:
  - Discuss code and technical concepts
  - Get explanations about existing code
  - Context-aware responses based on workspace content
  - Attach files for additional context

## Technical Stack

- **Backend**:
  - Flask web framework
  - Flask-SocketIO for WebSocket support
  - Eventlet for async operations

- **Frontend**:
  - Pure JavaScript
  - TailwindCSS for styling
  - CodeMirror for code editing
  - Socket.IO client for real-time notifications
  - PDF.js for PDF processing
  - Mammoth.js for Word documents
  - XLSX.js for Excel files
  - Tesseract.js for OCR
  - Marked and Unified.js for Markdown

## Installation

1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Set up your environment variables in `.env`:
   ```
   DEEPSEEK_API_KEY=your_deepseek_api_key
   CODESTRAL_API_KEY=your_codestral_api_key
   OPENROUTER_API_KEY=your_openrouter_api_key
   GOOGLE_API_KEY=your_google_api_key
   GROK_API_KEY=your_grok_api_key
   ANTHROPIC_API_KEY=your_anthropic_api_key
   OPENAI_API_KEY=your_openai_api_key
   ```

## Usage

1. Start the server:
   ```bash
   python app.py
   ```
2. Open your browser and navigate to `http://localhost:5000`
3. Create a new workspace or select an existing one
4. Choose your preferred AI model
5. Start coding with AI assistance!

## Model Capabilities

- **DeepSeek R1**: Latest DeepSeek model with enhanced code understanding and generation
- **DeepSeek V3**: Specialized in code generation and modification
- **Codestral**: High-performance code generation model
- **Gemini 2.0 Pro**: Advanced code generation and natural language understanding
- **Grok 2**: Advanced language model for code and natural language
- **Claude 3.5 Sonnet**: Advanced reasoning and code understanding
- **GPT-4 Turbo**: Latest GPT-4 model with improved performance and up-to-date knowledge
- **GPT-4o Mini**: Experimental model with specialized capabilities and unique instruction handling
- **GPT-4o**: Optimized GPT-4 variant with enhanced code understanding
- **o1-mini**: Experimental model with specialized capabilities and unique instruction handling
- **o1-preview**: Experimental model with specialized capabilities and unique instruction handling

## Contributing

Contributions are welcome! Please feel free to submit pull requests.

## Special Thanks

- **Nikole Cardoso** for her invaluable contributions and support
- **Guilherme Guirro** for his expertise and guidance
- **Felipe Santos** for his dedication and insights

Their contributions have been instrumental in making J.A.R.V.I.S. better.

## Platform Compatibility

This application has been tested and confirmed working on:
- Linux (native)
- Windows Subsystem for Linux (WSL 2)
- Windows (native, no admin privileges required)

The application uses directory junctions on Windows to avoid requiring admin privileges, while maintaining symlink functionality on Unix-like systems.

## License

This project is licensed under the MIT License - see the [LICENSE.md](LICENSE.md) file for details.