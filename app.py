"""Main application module"""

# pylama:ignore=E501,C901
import eventlet
eventlet.monkey_patch()

import json
import os
import shutil
import time
from datetime import datetime

import google.generativeai as genai
from anthropic import Anthropic
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, send_from_directory
from flask_socketio import SocketIO
from openai import OpenAI

from terminal_manager import TerminalManager
from workspace_manager import WorkspaceManager


# Model configurations
AVAILABLE_MODELS = {
    "deepseek-r1": {
        "name": "DeepSeek R1",
        "api_key_env": "DEEPSEEK_API_KEY",
        "client_class": OpenAI,
        "base_url": "https://api.deepseek.com",
        "models": {
            "code": "deepseek-reasoner",
            "chat": "deepseek-reasoner"
        },
        "max_tokens": 100000,
    },
    "deepseek": {
        "name": "DeepSeek V3",
        "api_key_env": "DEEPSEEK_API_KEY",
        "client_class": OpenAI,
        "base_url": "https://api.deepseek.com",
        "models": {
            "code": "deepseek-chat",
            "chat": "deepseek-chat"
        },
        "max_tokens": 100000,
    },
    "deepseek-openrouter": {
        "name": "DeepSeek V3 (OpenRouter)",
        "api_key_env": "OPENROUTER_API_KEY",
        "client_class": OpenAI,
        "base_url": "https://openrouter.ai/api/v1",
        "models": {
            "code": "deepseek/deepseek-chat",
            "chat": "deepseek/deepseek-chat"
        },
        "max_tokens": 100000,
    },
    "codestral": {
        "name": "Codestral",
        "api_key_env": "CODESTRAL_API_KEY",
        "client_class": OpenAI,
        "base_url": "https://codestral.mistral.ai/v1",
        "models": {
            "code": "codestral-latest",
            "chat": "codestral-latest"
        },
        "max_tokens": 100000,
    },
    "gemini": {
        "name": "Gemini 2.0 Flash Experimental",
        "api_key_env": "GOOGLE_API_KEY",
        "client_class": "genai",
        "models": {
            "code": "gemini-2.0-flash-exp",
            "chat": "gemini-2.0-flash-exp"
        },
        "max_tokens": 30000,
    },
    "grok": {
        "name": "Grok 2",
        "api_key_env": "GROK_API_KEY",
        "client_class": OpenAI,
        "base_url": "https://api.x.ai/v1",
        "models": {
            "code": "grok-2-latest",
            "chat": "grok-2-latest"
        },
        "max_tokens": 100000,
    },
    "claude": {
        "name": "Claude 3.5 Sonnet",
        "api_key_env": "ANTHROPIC_API_KEY",
        "client_class": Anthropic,
        "models": {
            "code": "claude-3-5-sonnet-20241022",
            "chat": "claude-3-5-sonnet-20241022",
        },
        "max_tokens": 100000,
    },
    "gpt-4-turbo": {
        "name": "GPT-4 Turbo",
        "api_key_env": "OPENAI_API_KEY",
        "client_class": OpenAI,
        "models": {
            "code": "gpt-4-turbo",
            "chat": "gpt-4-turbo"
        },
        "max_tokens": 100000,
    },
    "gpt-4o-mini": {
        "name": "GPT-4o-mini",
        "api_key_env": "OPENAI_API_KEY",
        "client_class": OpenAI,
        "models": {
            "code": "gpt-4o-mini",
            "chat": "gpt-4o-mini"
        },
        "max_tokens": 100000,
    },
    "gpt-4o": {
        "name": "GPT-4o",
        "api_key_env": "OPENAI_API_KEY",
        "client_class": OpenAI,
        "models": {
            "code": "gpt-4o",
            "chat": "gpt-4o"
        },
        "max_tokens": 100000,
    },
    "o1-mini": {
        "name": "o1-mini",
        "api_key_env": "OPENAI_API_KEY",
        "client_class": OpenAI,
        "models": {
            "code": "o1-mini",
            "chat": "o1-mini"
        },
        "max_tokens": 100000,
    },
    "o1": {
        "name": "o1-preview",
        "api_key_env": "OPENAI_API_KEY",
        "client_class": OpenAI,
        "models": {
            "code": "o1-preview",
            "chat": "o1-preview"
        },
        "max_tokens": 100000,
    },
}

# System prompt for code generation
system_prompt = """You are an expert AI coding assistant. Your task is to help users with any coding-related request.

IMPORTANT: Before suggesting any changes:
1. ALWAYS read the current content of the file first
2. Analyze the content to understand the current state
3. Only specify the exact changes needed
4. Do not include unchanged content

When you see files marked with [ATTACHMENT], these are additional files provided by the user for context. Use them to:
1. Understand code patterns and styles to maintain consistency
2. Reference implementations or examples
3. Extract relevant code snippets or configurations
4. Follow similar patterns when generating new code

Your responses must be formatted as a valid JSON object with this structure:
{
    "explanation": "Brief explanation of what you will do",
    "operations": [
        {
            "type": "edit_file",
            "path": "relative/path",
            "changes": [
                {
                    "old": "text to replace",
                    "new": "replacement text"
                }
            ],
            "explanation": "why this change is needed"
        }
    ]
}

Operation types can include but are not limited to:
- create_file: Create a new file (requires complete content)
- edit_file: Specify only the changes needed
- remove_file: Delete a file
- rename_file: Rename/move a file (requires new_path)
- remove_directory: Delete a directory (requires recursive boolean)

Guidelines for operations:
1. First read and analyze the existing file
2. When a file needs multiple operations (e.g., content changes AND rename):
   - First use edit_file to modify the content
   - Then use rename_file to move/rename the file
   - Each operation should be a separate entry in the operations array
3. For modifying content:
   - Only specify the exact text to change
   - Use the "changes" array to list each modification
   - For simple text replacements (e.g., replacing all instances of "nginx" with "apache"),
     include just one change with the exact text to replace
   - For complex code changes, include each specific change separately
4. For renaming files:
   - Use the rename_file operation type
   - Specify both path (current) and new_path (target)
   - If content also needs to change, do that in a separate edit_file operation first

IMPORTANT:
- ALWAYS read the file content first
- ONLY specify the changes needed
- NEVER return unchanged content
- ALWAYS preserve the file's existing style and formatting
- When both renaming and editing a file, do BOTH operations in the correct order
- When attachments are provided, use them as reference for code style and patterns

Respond with a single, valid JSON object."""

# Initialize clients for each model
load_dotenv()

model_clients = {}
for model_id, config in AVAILABLE_MODELS.items():
    api_key = os.getenv(config["api_key_env"])
    if api_key:
        if config["client_class"] == "genai":
            genai.configure(api_key=api_key)
            model_clients[model_id] = genai
        else:
            client_kwargs = {"api_key": api_key}
            # Add base_url if specified
            if "base_url" in config:
                client_kwargs["base_url"] = config["base_url"]

            model_clients[model_id] = config["client_class"](**client_kwargs)

app = Flask(__name__)
app.secret_key = os.urandom(24)  # For session management
socketio = SocketIO(app, cors_allowed_origins="*")

# Set up workspace directory
WORKSPACE_ROOT = os.path.join(os.getcwd(), "workspaces")
os.makedirs(WORKSPACE_ROOT, exist_ok=True)

# Initialize workspace manager
workspace_manager = WorkspaceManager(WORKSPACE_ROOT)

# Store terminal managers for each client
terminal_managers = {}


@app.route("/")
def index():
    return render_template("base.html")


@socketio.on("connect")
def handle_connect():
    print(f"Client connected: {request.sid}")


@socketio.on("disconnect")
def handle_disconnect():
    # Cleanup terminal if it exists
    if request.sid in terminal_managers:
        terminal_managers[request.sid].cleanup()
        del terminal_managers[request.sid]
    print(f"Client disconnected: {request.sid}")


@socketio.on("terminal_init")
def handle_terminal_init(data):
    # Create new terminal manager for this client
    terminal_managers[request.sid] = TerminalManager(socketio)
    terminal_managers[request.sid].start(data["cols"], data["rows"])


@socketio.on("terminal_input")
def handle_terminal_input(data):
    if request.sid in terminal_managers:
        terminal_managers[request.sid].write(data["data"])


@socketio.on("terminal_resize")
def handle_terminal_resize(data):
    if request.sid in terminal_managers:
        terminal_managers[request.sid].resize_terminal(data["cols"],
                                                       data["rows"])


def create_workspace():
    """Create a new workspace directory"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    workspace_id = timestamp
    workspace_path = os.path.join(WORKSPACE_ROOT, workspace_id)
    os.makedirs(workspace_path, exist_ok=True)
    return workspace_id, workspace_path


def get_workspace_history():
    """Get list of all workspaces with their history"""
    workspaces = []

    # List all directories in WORKSPACE_ROOT
    for item in os.listdir(WORKSPACE_ROOT):
        workspace_path = os.path.join(WORKSPACE_ROOT, item)
        if os.path.isdir(workspace_path):
            # Get directory creation time
            created_at = datetime.fromtimestamp(
                os.path.getctime(workspace_path))

            # Count files in workspace using workspace_manager's logic
            total_files = 0
            for root, dirs, files in os.walk(workspace_path):
                # Skip .git and other ignored directories
                dirs[:] = [
                    d for d in dirs if not d.startswith(".")
                    and d not in workspace_manager.SKIP_FOLDERS
                ]

                # Filter files based on gitignore and skip patterns
                for file in files:
                    if not file.startswith(".") and not file.endswith(
                            tuple(workspace_manager.SKIP_EXTENSIONS)):
                        rel_path = os.path.relpath(os.path.join(root, file),
                                                   workspace_path)
                        if not workspace_manager._should_ignore(rel_path):
                            total_files += 1

            # Check if this is an imported workspace
            is_imported = os.path.exists(
                os.path.join(workspace_path, ".imported"))

            workspaces.append({
                "id": item,
                "path": workspace_path,
                "created_at": created_at.isoformat(),
                "file_count": total_files,
                "is_imported": is_imported,
            })

    # Sort alphabetically by ID, case-insensitive
    return sorted(workspaces, key=lambda x: x["id"].lower())


def delete_workspace(workspace_id):
    """Delete a workspace"""
    try:
        workspace_path = os.path.join(WORKSPACE_ROOT, workspace_id)

        # Verify the path is within WORKSPACE_ROOT for safety
        if not os.path.abspath(workspace_path).startswith(
                os.path.abspath(WORKSPACE_ROOT)):
            raise Exception("Invalid workspace path")

        # Check if it's an imported workspace
        if os.path.exists(os.path.join(workspace_path, ".imported")):
            # Remove the .imported file
            os.remove(os.path.join(workspace_path, ".imported"))

            if os.name == "nt":  # Windows
                import subprocess

                try:
                    # Use rmdir to remove directory junction
                    subprocess.run(["cmd", "/c", "rmdir", workspace_path],
                                   check=True)
                except subprocess.CalledProcessError as e:
                    raise Exception(
                        f"Failed to remove directory junction: {str(e)}")
            else:
                # Remove symlink on Unix-like systems
                os.unlink(workspace_path)
        else:
            # Delete directory for regular workspaces
            try:
                if os.path.exists(workspace_path):
                    shutil.rmtree(workspace_path, ignore_errors=False)
                if os.path.exists(workspace_path):
                    raise Exception("Failed to delete workspace directory")
            except Exception as e:
                raise Exception(
                    f"Failed to delete workspace directory: {str(e)}")

        return True
    except Exception as e:
        raise Exception(f"Failed to delete workspace: {str(e)}")


def get_workspace_structure(workspace_dir):
    structure = []

    # Check if this is an imported workspace
    is_imported = os.path.exists(os.path.join(workspace_dir, ".imported"))

    for root, dirs, files in os.walk(workspace_dir):
        rel_path = os.path.relpath(root, workspace_dir)
        if rel_path == ".":
            rel_path = ""

        # Skip hidden directories and files
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        files = [f for f in files if not f.startswith(".")]

        for name in dirs:
            full_path = os.path.join(root, name)
            rel_full_path = os.path.relpath(full_path, workspace_dir)

            structure.append({
                "name": name,
                "type": "directory",
                "path": rel_full_path.replace("\\", "/"),
                "imported":
                is_imported,  # Mark all folders as imported if workspace is imported
            })

        for name in files:
            full_path = os.path.join(root, name)
            rel_full_path = os.path.relpath(full_path, workspace_dir)

            structure.append({
                "name": name,
                "type": "file",
                "path": rel_full_path.replace("\\", "/"),
                "size": get_file_size(full_path),
            })

    return structure


def get_file_size(file_path):
    """Get the size of a file in bytes"""
    try:
        return os.path.getsize(file_path)
    except OSError:
        return 0


def read_file_in_chunks(file_path, chunk_size=8192):
    """Generator to read a file in chunks"""
    with open(file_path, "r", encoding="utf-8") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            yield chunk


def is_large_file(file_path, threshold_mb=5):
    """Check if a file is considered large (default threshold: 5MB)"""
    return get_file_size(file_path) > (threshold_mb * 1024 * 1024)


def get_file_preview(file_path, max_lines=1000):
    """Get a preview of a large file (first max_lines lines)"""
    preview_lines = []
    try:
        # First try UTF-8
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for i, line in enumerate(f):
                    if i >= max_lines:
                        preview_lines.append(
                            "... (file truncated, too large to display completely)"
                        )
                        break
                    preview_lines.append(line.rstrip("\n"))
        except UnicodeDecodeError:
            # If UTF-8 fails, try to detect if it's a binary file
            with open(file_path, "rb") as f:
                is_binary = False
                try:
                    chunk = f.read(1024)
                    if b"\x00" in chunk:
                        is_binary = True
                    # Try to decode as latin-1 which can handle all byte values
                    text = chunk.decode("latin-1")
                    if any(ord(c) < 32 and c not in "\r\n\t" for c in text):
                        is_binary = True
                except BaseException:
                    is_binary = True

                if is_binary:
                    return "[Binary file] - Cannot display content"

                # If not binary, try reading with latin-1 encoding
                f.seek(0)
                with open(file_path, "r", encoding="latin-1") as f:
                    for i, line in enumerate(f):
                        if i >= max_lines:
                            preview_lines.append(
                                "... (file truncated, too large to display completely)"
                            )
                            break
                        preview_lines.append(line.rstrip("\n"))

        return "\n".join(preview_lines)
    except Exception as e:
        return f"Error reading file: {str(e)}"


def get_existing_files(workspace_dir):
    """Get content of existing files in workspace"""
    # Validate workspace directory
    if not os.path.exists(workspace_dir) or not os.path.isdir(workspace_dir):
        raise ValueError("Invalid workspace directory")

    # Set maximum file size (50MB)
    MAX_FILE_SIZE = 50 * 1024 * 1024

    files_content = {}
    for root, _, files in os.walk(workspace_dir):
        for file in files:
            # Skip database, hidden files, and common binary formats
            if (not file.endswith(".db") and not file.startswith(".")
                    and not file.endswith((".pyc", ".pyo", ".pyd", ".so",
                                           ".dll", ".exe", ".bin"))):

                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, workspace_dir)
                try:
                    # Get file size
                    file_size = os.path.getsize(file_path)
                    if file_size > MAX_FILE_SIZE:
                        print(
                            f"Warning: Skipping large file {rel_path} ({file_size} bytes)"
                        )
                        continue

                    # Check if it's a large file
                    if is_large_file(file_path):
                        # For large files, only get a preview
                        preview = get_file_preview(file_path)
                        if preview.startswith("[Binary file]"):
                            continue  # Skip binary files
                        files_content[rel_path] = preview
                    else:
                        # Try UTF-8 first
                        try:
                            with open(file_path, "r", encoding="utf-8") as f:
                                content = f.read()
                        except UnicodeDecodeError:
                            # Check if binary
                            with open(file_path, "rb") as f:
                                chunk = f.read(1024)
                                if b"\x00" in chunk:
                                    continue  # Skip binary files

                                # Try latin-1 as fallback
                                try:
                                    with open(file_path,
                                              "r",
                                              encoding="latin-1") as f:
                                        content = f.read()
                                except BaseException:
                                    continue  # Skip if still can't read

                        files_content[rel_path] = content
                except Exception as e:
                    print(f"Warning: Could not read file {file_path}: {e}")
                    continue
    return files_content


@app.route("/workspace/create", methods=["POST"])
def create_new_workspace():
    try:
        workspace_id, workspace_dir = create_workspace()

        # Return empty structure for new workspace
        structure = []

        return jsonify({
            "status": "success",
            "workspace_id": workspace_id,
            "workspace_dir": workspace_dir,
            "structure": structure,
        })
    except Exception as e:
        print(f"Error creating workspace: {str(e)}")  # Add debug logging
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/workspace/history", methods=["GET"])
def get_history():
    try:
        history = get_workspace_history()
        return jsonify({"status": "success", "history": history})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/workspace/structure", methods=["POST"])
def get_workspace_structure_route():
    try:
        data = request.get_json()
        workspace_dir = data.get("workspace_dir")

        if not workspace_dir or not os.path.exists(workspace_dir):
            return jsonify({
                "status": "error",
                "message": "Invalid workspace directory"
            })

        structure = workspace_manager.get_workspace_structure(workspace_dir)
        return jsonify({"status": "success", "structure": structure})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@app.route("/workspace/expand", methods=["POST"])
def expand_directory():
    try:
        data = request.get_json()
        workspace_dir = data.get("workspace_dir")
        dir_path = data.get("dir_path")
        page = int(data.get("page", 1))
        page_size = int(data.get("page_size", 100))

        print("\nExpanding directory request:")  # Debug log
        print(f"Workspace: {workspace_dir}")
        print(f"Directory: {dir_path}")
        print(f"Page: {page}, Page Size: {page_size}")

        if not workspace_dir or not os.path.exists(workspace_dir):
            print(f"Invalid workspace directory: {workspace_dir}")  # Debug log
            return (
                jsonify({
                    "status": "error",
                    "message": "Invalid workspace directory"
                }),
                400,
            )

        if not dir_path:
            print("No directory path provided")  # Debug log
            return (
                jsonify({
                    "status": "error",
                    "message": "Directory path not provided"
                }),
                400,
            )

        try:
            result = workspace_manager.expand_directory(
                dir_path=dir_path,
                workspace_dir=workspace_dir,
                page_size=page_size,
                page=page,
            )
            # Debug log
            print(f"Expansion successful: {len(result['items'])} items")
            return jsonify({
                "status": "success",
                "items": result["items"],
                "total_items": result["total_items"],
                "has_more": result["has_more"],
            })
        except ValueError as e:
            print(f"Validation error: {str(e)}")  # Debug log
            return jsonify({"status": "error", "message": str(e)}), 400
        except Exception as e:
            print(f"Unexpected error: {str(e)}")  # Debug log
            return (
                jsonify({
                    "status": "error",
                    "message": f"Failed to expand directory: {str(e)}",
                }),
                500,
            )

    except Exception as e:
        print(f"Request processing error: {str(e)}")  # Debug log
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/process", methods=["POST"])
def process_prompt():
    try:
        data = request.json
        prompt = data.get("prompt")
        workspace_dir = data.get("workspace_dir")
        model_id = data.get("model_id")
        attachments = data.get("attachments", [])
        context_path = data.get("context_path")  # Get the context path

        if not prompt:
            return jsonify({
                "status": "error",
                "message": "No prompt provided"
            }), 400

        if not model_id:
            return jsonify({
                "status": "error",
                "message": "No model selected"
            }), 400

        if not workspace_dir:
            socketio.emit("status", {
                "message": "Creating new workspace...",
                "step": 0
            })
            _, workspace_dir = create_workspace()
        elif not os.path.exists(workspace_dir):
            return (
                jsonify({
                    "status": "error",
                    "message": "Invalid workspace directory"
                }),
                400,
            )

        # Use workspace manager to get relevant files based on the query and
        # context
        socketio.emit("status", {
            "message": "Reading workspace files...",
            "step": 1
        })

        # If we have a context path, prioritize that file/folder
        if context_path:
            full_path = os.path.join(workspace_dir, context_path)
            if os.path.exists(full_path):
                if os.path.isfile(full_path):
                    # For a file, get its content directly
                    content = workspace_manager._get_file_content(full_path)
                    files_content = {context_path: content} if content else {}
                else:
                    # For a directory, get contents of files within it
                    files_content = workspace_manager.get_workspace_files(
                        full_path)
        else:
            # No context path, get relevant files based on the query
            files_content = workspace_manager.get_workspace_files(
                workspace_dir, query=prompt)

        # Add attachment contents to files_content
        if attachments:
            for attachment in attachments:
                files_content[
                    f"[ATTACHMENT] {attachment['name']}"] = attachment[
                        "content"]

        # Get suggestions from AI
        suggestions = get_code_suggestion(prompt=prompt,
                                       files_content=files_content,
                                       model_id=model_id,
                                       workspace_context=None)

        if not suggestions or "operations" not in suggestions:
            return (
                jsonify({
                    "status": "error",
                    "message": "No valid suggestions received"
                }),
                400,
            )

        # Process operations to add diffs
        suggestions["operations"] = workspace_manager.process_operations(
            suggestions["operations"], workspace_dir)

        # Always generate diffs for all operations
        for operation in suggestions["operations"]:
            if operation["type"] in ["edit_file", "create_file"]:
                diff_info = get_operation_diff(operation, workspace_dir)
                # Add diff information to the operation
                operation.update(diff_info)

                # Ensure we have the content field for all operations
                if "content" not in operation:
                    operation["content"] = diff_info["new_content"]

                print(f"Generated diff for {operation['path']}:")
                print(diff_info["diff"])

        # Apply changes if no approval needed
        if not suggestions.get("requires_approval", True):
            results = apply_changes(suggestions, workspace_dir)
            structure = workspace_manager.get_workspace_structure(
                workspace_dir)

            return jsonify({
                "status": "success",
                "workspace_dir": workspace_dir,
                "structure": structure,
                "results": results,
            })

        # Return suggestions for approval
        structure = workspace_manager.get_workspace_structure(workspace_dir)
        return jsonify({
            "status": "success",
            "workspace_dir": workspace_dir,
            "structure": structure,
            "suggestions": suggestions,
            "requires_approval": True,
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/workspace/delete", methods=["POST"])
def delete_workspace_endpoint():
    try:
        data = request.json
        workspace_id = data.get("workspace_id")

        if not workspace_id:
            return jsonify({"error": "No workspace ID provided"}), 400

        delete_workspace(workspace_id)
        return jsonify({
            "status": "success",
            "message": "Workspace deleted successfully"
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/workspace/file", methods=["POST"])
def get_file_content():
    try:
        data = request.json
        workspace_dir = data.get("workspace_dir")
        file_path = data.get("file_path")

        if not workspace_dir or not file_path:
            return (
                jsonify({
                    "status": "error",
                    "message": "Missing workspace_dir or file_path"
                }),
                400,
            )

        # Validate file path to prevent directory traversal
        if ".." in file_path or file_path.startswith("/"):
            return jsonify({
                "status": "error",
                "message": "Invalid file path"
            }), 400

        # Get the full path by joining workspace_dir and file_path
        full_path = os.path.normpath(os.path.join(workspace_dir, file_path))

        print(f"Workspace: {workspace_dir}")  # Debug log
        print(f"File path: {file_path}")  # Debug log
        print(f"Full path: {full_path}")  # Debug log

        if not os.path.abspath(full_path).startswith(
                os.path.abspath(workspace_dir)):
            return (
                jsonify({
                    "status": "error",
                    "message": "File path not within workspace"
                }),
                400,
            )

        if not os.path.exists(full_path):
            print(f"File not found: {full_path}")  # Debug log
            return jsonify({
                "status": "success",
                "content": "",  # Return empty content for new files
                "file_size": 0,
                "truncated": False,
            })

        # Use workspace manager to get file content
        content = workspace_manager._get_file_content(full_path)
        file_size = os.path.getsize(full_path)
        is_large = workspace_manager.is_large_file(full_path)

        return jsonify({
            "status": "success",
            "content": content,
            "truncated": is_large,
            "file_size": file_size,
        })

    except Exception as e:
        print(f"Error in get_file_content: {str(e)}")  # Debug log
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/workspace/rename", methods=["POST"])
def rename_workspace():
    """Rename a workspace"""
    data = request.json
    workspace_id = data.get("workspace_id")
    new_name = data.get("new_name")

    if not workspace_id or not new_name:
        return (
            jsonify({
                "status": "error",
                "message": "Missing workspace_id or new_name"
            }),
            400,
        )

    try:
        old_path = os.path.join(WORKSPACE_ROOT, workspace_id)
        new_path = os.path.join(WORKSPACE_ROOT, new_name)

        # Check if source exists and target doesn't
        if not os.path.exists(old_path):
            return jsonify({
                "status": "error",
                "message": "Workspace not found"
            }), 404

        if os.path.exists(new_path):
            return (
                jsonify({
                    "status": "error",
                    "message": "A workspace with this name already exists",
                }),
                400,
            )

        # Rename directory
        os.rename(old_path, new_path)

        return jsonify({
            "status": "success",
            "message": "Workspace renamed successfully",
            "new_path": new_path,
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.json
        prompt = data.get("prompt")
        workspace_dir = data.get("workspace_dir")
        model_id = data.get("model_id")
        attachments = data.get("attachments", [])
        context_path = data.get("context_path")  # Get the context path

        if not prompt:
            return jsonify({"error": "No prompt provided"}), 400

        if not model_id:
            return jsonify({"error": "No model selected"}), 400

        if not workspace_dir or not os.path.exists(workspace_dir):
            return jsonify({"error": "Invalid workspace directory"}), 400

        # If we have a context path, prioritize that file/folder
        if context_path:
            full_path = os.path.join(workspace_dir, context_path)
            if os.path.exists(full_path):
                if os.path.isfile(full_path):
                    # For a file, get its content directly
                    with open(full_path, "r", encoding="utf-8") as f:
                        files_content = {context_path: f.read()}
                else:
                    # For a directory, get contents of files within it
                    files_content = {}
                    for root, _, files in os.walk(full_path):
                        for file in files:
                            if not file.startswith(".") and not file.endswith(
                                    tuple(workspace_manager.SKIP_EXTENSIONS)):
                                file_path = os.path.join(root, file)
                                rel_path = os.path.relpath(
                                    file_path, workspace_dir)
                                try:
                                    with open(file_path, "r",
                                              encoding="utf-8") as f:
                                        files_content[rel_path] = f.read()
                                except Exception as e:
                                    print(
                                        f"Error reading file {file_path}: {e}")
        else:
            # No context path, get relevant files based on the query
            files_content = workspace_manager.get_workspace_files(
                workspace_dir, query=prompt)

        # Add attachment contents to the context
        if attachments:
            for attachment in attachments:
                files_content[
                    f"[ATTACHMENT] {attachment['name']}"] = attachment[
                        "content"]

        # Build context from files
        context = "Here are the relevant files in the workspace:\n\n"
        for file_path, content in files_content.items():
            context += f"File: {file_path}\nContent:\n{content}\n\n"

        # Construct a more focused system message based on context
        if context_path:
            if os.path.isfile(os.path.join(workspace_dir, context_path)):
                context_type = "file"
            else:
                context_type = "folder"
            system_message = f"""You are a helpful AI assistant powered by {AVAILABLE_MODELS[model_id]['name']} that can discuss code.
You are currently analyzing this specific {context_type}: {context_path}
{context}

Please provide helpful responses focused on this {context_type} and its contents."""
        else:
            system_message = f"""You are a helpful AI assistant powered by {AVAILABLE_MODELS[model_id]['name']} that can discuss the code in the workspace.
{context}

Please provide helpful responses about the code and files in this workspace."""

        response = get_chat_response(system_message, prompt, model_id)

        return jsonify({"status": "success", "response": response})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


def get_chat_response(system_message, user_message, model_id):
    """Get a chat response from the selected AI model"""
    if model_id not in model_clients:
        raise Exception(
            f"Model {model_id} is not configured. Please check your API keys.")

    client = model_clients[model_id]
    model_config = AVAILABLE_MODELS[model_id]

    try:
        print("\n=== Step 1: Preparing Chat Request ===")
        print(f"Model: {model_id}")

        # Create messages array for the chat
        if model_id == "o1-mini" or model_id == "o1":
            # For o1 model, combine system message and user message
            messages = [{
                "role":
                "user",
                "content":
                f"{system_message}\n\nUser request: {user_message}",
            }]
        else:
            messages = [
                {
                    "role": "system",
                    "content": system_message
                },
                {
                    "role": "user",
                    "content": user_message
                },
            ]

        # Estimate tokens in messages
        system_tokens = len(
            system_message.encode("utf-8")) // 4  # Rough estimate
        user_tokens = len(user_message.encode("utf-8")) // 4
        total_tokens = system_tokens + user_tokens

        # If total tokens exceed model's limit, truncate the system message
        max_tokens = model_config.get("max_tokens", 100000)
        if total_tokens > max_tokens:
            # Keep user message intact, truncate system message
            available_tokens = max_tokens - user_tokens - 1000  # Leave some buffer
            if available_tokens > 0:
                # Use workspace manager's truncation method
                system_message = workspace_manager._truncate_content_for_context(
                    system_message, max_tokens=available_tokens)
                # Update truncated message
                messages[0]["content"] = system_message
                print(
                    f"Truncated system message to fit within {available_tokens} tokens"
                )
            else:
                raise Exception("Message too long even after truncation")

        print(f"System message length: {len(system_message)} characters")
        print(f"User message length: {len(user_message)} characters")

        socketio.emit("status", {
            "message": "Sending chat request to AI model...",
            "step": 1
        })

        start_time = time.time()
        print("\n=== Step 2: Sending Request to AI Model ===")

        if model_id == "claude":
            # Use Anthropic's client interface
            response = client.messages.create(
                model=model_config["models"]["chat"],
                messages=[{
                    "role":
                    "user",
                    "content":
                    f"{system_message}\n\nUser request: {user_message}",
                }],
                temperature=0.7,
                max_tokens=4096,
            )
            if not response or not response.content:
                raise Exception("Empty response from Claude")
            text = response.content[0].text
            print(f"\nResponse received in {time.time() - start_time:.1f}s")
            print(f"Response length: {len(text)} characters")
        elif model_id == "gemini":
            # Use the Google AI client
            try:
                model = client.GenerativeModel("gemini-2.0-flash-exp")
                chat = model.start_chat(history=[])

                # Combine all messages into a single context
                full_context = "\n\n".join(msg["content"] for msg in messages)

                response = chat.send_message(
                    full_context,
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.1,
                        candidate_count=1,
                        max_output_tokens=8192),
                )

                if not response or not response.text:
                    raise Exception("Empty response from Gemini")

                # For chat, just use the text directly
                text = response.text.strip()
                print(
                    f"\nResponse received in {time.time() - start_time:.1f}s")
                print(f"Response length: {len(text)} characters")

            except Exception as e:
                error_msg = str(e)
                if "maximum context length" in error_msg.lower():
                    # Try again with more aggressive truncation
                    for i in range(len(messages) - 1):
                        if messages[i]["role"] == "system":
                            messages[i]["content"] = (
                                workspace_manager.
                                _truncate_content_for_context(
                                    messages[i]["content"],
                                    max_tokens=10000,  # Even more conservative
                                ))
                    # Combine truncated messages
                    full_context = "\n\n".join(msg["content"]
                                               for msg in messages)
                    response = chat.send_message(
                        full_context,
                        generation_config=genai.types.GenerationConfig(
                            temperature=0.1,
                            candidate_count=1,
                            max_output_tokens=4096),
                    )
                    if not response or not response.text:
                        raise Exception(
                            "Empty response from Gemini after truncation")
                    text = response.text.strip()
                else:
                    raise
        else:
            # Use streaming for other OpenAI-compatible models
            response = client.chat.completions.create(
                model=model_config["models"]["chat"],
                messages=messages,
                temperature=1 if model_id in ["o1-mini", "o1"] else 0.7,
                stream=True,
            )

            print("Request sent, waiting for response...")
            socketio.emit("status", {
                "message": "Receiving AI response...",
                "step": 2
            })

            # Process the streamed response
            text = ""
            chunk_count = 0
            last_update = time.time()
            update_interval = 0.5

            for chunk in response:
                if (chunk and hasattr(chunk.choices[0], "delta")
                        and hasattr(chunk.choices[0].delta, "content")):
                    content = chunk.choices[0].delta.content
                    if content is not None:
                        text += content
                        chunk_count += 1

                    current_time = time.time()
                    if current_time - last_update >= update_interval:
                        elapsed = current_time - start_time
                        tokens_per_second = chunk_count / elapsed if elapsed > 0 else 0
                        print(
                            f"\rReceived {chunk_count} chunks ({len(text)} chars) in {elapsed:.1f}s ({tokens_per_second:.1f} chunks/s)",
                            end="",
                        )
                        socketio.emit(
                            "status",
                            {
                                "message":
                                f"Receiving chat response... ({len(text)} characters)",
                                "step": 2,
                                "progress": {
                                    "chunks": chunk_count,
                                    "chars": len(text),
                                    "elapsed": elapsed,
                                    "rate": tokens_per_second,
                                },
                            },
                        )
                        last_update = current_time

            print(f"\nResponse complete in {time.time() - start_time:.1f}s")
            print(
                f"Total response size: {len(text)} characters in {chunk_count} chunks"
            )

        print("\n=== Step 3: Formatting Response ===")
        socketio.emit("status", {
            "message": "Formatting response...",
            "step": 3
        })

        # Split text into code blocks and regular text
        parts = text.split("```")
        formatted_parts = []

        for i, part in enumerate(parts):
            if i % 2 == 0:  # Regular text
                # Replace newlines with <br> in regular text
                formatted_parts.append(part.replace("\n", "<br>"))
            else:  # Code block
                # Extract language if specified
                if "\n" in part:
                    lang, code = part.split("\n", 1)
                    # Remove trailing whitespace and newlines, preserve
                    # indentation
                    formatted_code = (code.rstrip().replace("\n",
                                                            "<br>").replace(
                                                                " ", "&nbsp;"))
                    formatted_parts.append(
                        f'<pre><code class="language-{lang.strip()}">{formatted_code}</code></pre>'
                    )
                else:
                    # Single line code block, remove trailing whitespace
                    formatted_parts.append(
                        f'<pre><code>{part.strip().replace(" ", "&nbsp;")}</code></pre>'
                    )

        formatted_text = "".join(formatted_parts)
        print("Response formatting complete")

        socketio.emit("status", {"message": "Response ready", "step": 4})
        return formatted_text

    except Exception as e:
        socketio.emit("status", {"message": f"Error: {str(e)}", "step": -1})
        print(f"\nError getting chat response: {str(e)}")
        raise


@app.route("/models", methods=["GET"])
def get_available_models():
    """Get list of available and configured models"""
    configured_models = []
    for model_id, config in AVAILABLE_MODELS.items():
        if model_id in model_clients:
            configured_models.append({"id": model_id, "name": config["name"]})
    return jsonify({"status": "success", "models": configured_models})


@app.route("/logo.svg")
def serve_logo():
    return send_from_directory("static", "logo.svg", mimetype="image/svg+xml")


@app.route("/favicon.png")
def serve_favicon():
    return send_from_directory("static",
                               "favicon.svg",
                               mimetype="image/svg+xml")


@app.route("/apply_changes", methods=["POST"])
def apply_changes_endpoint():
    try:
        data = request.json
        workspace_dir = data.get("workspace_dir")
        operations = data.get("operations", [])

        if not workspace_dir:
            return (
                jsonify({
                    "status": "error",
                    "message": "No workspace directory provided"
                }),
                400,
            )

        if not operations:
            return (
                jsonify({
                    "status": "error",
                    "message": "No operations to apply"
                }),
                400,
            )

        # Apply the changes
        results = apply_changes({"operations": operations}, workspace_dir)

        # Get updated workspace structure
        structure = workspace_manager.get_workspace_structure(workspace_dir)

        return jsonify({
            "status": "success",
            "structure": structure,
            "results": results
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.context_processor
def utility_processor():
    """Add utility functions to template context"""
    return {"cache_buster": str(int(datetime.now().timestamp()))}


def get_workspace_context(workspace_dir):
    """Get a description of the workspace context"""
    structure = get_workspace_structure(workspace_dir)
    files_content = get_existing_files(workspace_dir)

    context = "Workspace Structure:\n"
    for item in structure:
        prefix = "📁 " if item["type"] == "directory" else " "
        context += f"{prefix}{item['path']}\n"

    context += "\nFile Relationships and Dependencies:\n"
    # Analyze imports and dependencies
    dependencies = analyze_dependencies(files_content)
    for file, deps in dependencies.items():
        if deps:
            context += f"{file} depends on: {', '.join(deps)}\n"

    return context


def analyze_dependencies(files_content):
    """Analyze file dependencies based on imports and references"""
    dependencies = {}
    import_patterns = {
        ".py": ["import ", "from "],
        ".js": ["import ", "require("],
        ".html": ["<script src=", "<link href="],
    }

    for file_path, content in files_content.items():
        ext = os.path.splitext(file_path)[1]
        deps = set()

        if ext in import_patterns:
            lines = content.split("\n")
            for line in lines:
                for pattern in import_patterns[ext]:
                    if pattern in line:
                        # Extract dependency name (simplified)
                        dep = line.split(pattern)[-1].split()[0].strip("\"';")
                        deps.add(dep)

        dependencies[file_path] = deps

    return dependencies


def run_linter(file_path):
    """Run pylama for multi-language linting support"""
    try:
        import subprocess
        from pathlib import Path

        # Get file extension
        file_ext = Path(file_path).suffix.lower()

        # Skip binary files and common non-text formats
        binary_extensions = {
            # Binary files
            ".pyc",
            ".pyo",
            ".so",
            ".dll",
            ".exe",
            ".bin",
            # Images
            ".jpg",
            ".jpeg",
            ".png",
            ".gif",
            ".bmp",
            ".ico",
            ".webp",
            # Documents
            ".pdf",
            ".doc",
            ".docx",
            ".xls",
            ".xlsx",
            ".ppt",
            ".pptx",
            # Archives
            ".zip",
            ".tar",
            ".gz",
            ".rar",
            ".7z",
            # Media
            ".mp3",
            ".mp4",
            ".avi",
            ".mov",
            ".wav",
            # Other binaries
            ".db",
            ".sqlite",
            ".class",
            ".o",
        }
        if file_ext in binary_extensions:
            return True

        # Run pylama with appropriate configuration
        try:
            result = subprocess.run(
                ["pylama", file_path],
                capture_output=True,
                text=True,
                timeout=30,  # Add timeout to prevent hanging
            )
            # Print linting output for debugging
            if result.stdout or result.stderr:
                print(f"\nLinting output for {file_path}:")
                if result.stdout:
                    print("stdout:", result.stdout)
                if result.stderr:
                    print("stderr:", result.stderr)
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            print(f"Linting timeout for {file_path}")
            return False
        except subprocess.CalledProcessError as e:
            print(f"Linting process error for {file_path}: {e}")
            return False

    except Exception as e:
        print(f"Linting error for {file_path}: {str(e)}")
        return False


def apply_changes(suggestions, workspace_dir):
    """Apply the suggested changes to the workspace"""
    results = []

    try:
        for operation in suggestions["operations"]:
            try:
                # Add linter status field
                operation["linter_status"] = True  # Default to True

                if operation["type"] == "edit_file":
                    file_path = os.path.join(workspace_dir, operation["path"])

                    # Read the current content
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()

                    # Apply the changes
                    new_content = content
                    for change in operation["changes"]:
                        if "old" in change and "new" in change:
                            new_content = new_content.replace(change["old"],
                                                              change["new"])
                    # Store the new content in the operation
                    operation["content"] = new_content

                    # Write the updated content
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(new_content)

                    # Run appropriate linter
                    operation["linter_status"] = workspace_manager.run_linter(
                        file_path)

                    results.append({
                        "status": "success",
                        "operation": operation
                    })

                elif operation["type"] == "create_file":
                    # Create the file
                    file_path = os.path.join(workspace_dir, operation["path"])
                    os.makedirs(os.path.dirname(file_path), exist_ok=True)

                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(operation["content"])

                    # Run appropriate linter
                    operation["linter_status"] = workspace_manager.run_linter(
                        file_path)

                    results.append({
                        "status": "success",
                        "operation": operation
                    })

                elif operation["type"] == "rename_file":
                    old_path = os.path.join(workspace_dir, operation["path"])
                    new_path = os.path.join(workspace_dir,
                                            operation["new_path"])

                    # Create target directory if it doesn't exist
                    os.makedirs(os.path.dirname(new_path), exist_ok=True)

                    # Rename the file
                    os.rename(old_path, new_path)

                    # No linting needed for rename operations
                    operation["linter_status"] = True

                    results.append({
                        "status": "success",
                        "operation": operation
                    })

                elif operation["type"] == "remove_file":
                    file_path = os.path.join(workspace_dir, operation["path"])
                    os.remove(file_path)
                    results.append({
                        "status": "success",
                        "operation": operation
                    })

            except Exception as e:
                results.append({
                    "status": "error",
                    "operation": operation,
                    "error": str(e)
                })

        # Notify all clients about the changes
        workspace_id = os.path.basename(workspace_dir)
        modified_files = [
            result["operation"]["path"] for result in results
            if result["status"] == "success"
        ]
        socketio.emit(
            "changes_applied",
            {
                "workspace_id": workspace_id,
                "modified_files": modified_files
            },
        )

        return results
    except Exception as e:
        raise Exception(f"Failed to apply changes: {str(e)}")


def get_code_suggestion(prompt,
                        files_content=None,
                        model_id=None,
                        workspace_context=None):
    """Get code suggestions from the selected AI model"""
    if model_id not in model_clients:
        raise Exception(
            f"Model {model_id} is not configured. Please check your API keys.")

    client = model_clients[model_id]
    model_config = AVAILABLE_MODELS[model_id]

    try:
        print("\n=== Step 1: Preparing AI Request ===")
        print(f"Model: {model_id}")
        print(f"Prompt length: {len(prompt)} characters")

        # Create the messages array for the chat
        if model_id in ["o1", "o1-mini"]:
            messages = []
            # Combine all system messages into a single user message
            system_content = [system_prompt]
            if workspace_context:
                system_content.append(
                    f"Workspace context:\n{workspace_context}")
            if files_content:
                files_content_str = "Files content:\n"
                for path, content in files_content.items():
                    files_content_str += f"\nFile: {path}\nContent:\n{content}\n"
                system_content.append(files_content_str)
            system_content.append(
                f'{prompt}\n\nIMPORTANT: Your response MUST be a valid JSON object following this exact structure:\n{{\n    "explanation": "Brief explanation of what you will do",\n    "operations": [\n        {{\n            "type": "edit_file",\n            "path": "relative/path",\n            "changes": [\n                {{\n                    "old": "text to replace",\n                    "new": "replacement text"\n                }}\n            ]\n        }}\n    ]\n}}'
            )
            messages = [{
                "role": "user",
                "content": "\n\n".join(system_content)
            }]
        else:
            messages = [{"role": "system", "content": system_prompt}]

            # Add workspace context if provided
            if workspace_context:
                print("\nAdding workspace context...")
                messages.append({
                    "role":
                    "system",
                    "content":
                    f"Workspace context:\n{workspace_context}",
                })

            # Add files content if provided
            if files_content:
                files_content_str = "Files content:\n"
                for path, content in files_content.items():
                    files_content_str += f"\nFile: {path}\nContent:\n{content}\n"
                messages.append({
                    "role": "system",
                    "content": files_content_str
                })

            # Add the user's prompt with explicit JSON instruction
            messages.append({
                "role":
                "user",
                "content":
                f'{prompt}\n\nIMPORTANT: Your response MUST be a valid JSON object following this exact structure:\n{{\n    "explanation": "Brief explanation of what you will do",\n    "operations": [\n        {{\n            "type": "edit_file",\n            "path": "relative/path",\n            "changes": [\n                {{\n                    "old": "text to replace",\n                    "new": "replacement text"\n                }}\n            ]\n        }}\n    ]\n}}',
            })

        # Estimate total tokens
        total_tokens = sum(
            len(msg["content"].encode("utf-8")) // 4 for msg in messages)
        max_tokens = model_config.get("max_tokens", 100000)

        # If total tokens exceed model's limit, truncate the system messages
        if total_tokens > max_tokens:
            # Keep prompt intact, truncate context
            available_tokens = (max_tokens -
                                (len(prompt.encode("utf-8")) // 4) - 1000
                                )  # Leave buffer
            if available_tokens > 0:
                # Truncate each system message proportionally
                for i in range(len(messages) -
                               1):  # Skip the last message (user prompt)
                    if messages[i]["role"] == "system":
                        messages[i]["content"] = (
                            workspace_manager._truncate_content_for_context(
                                messages[i]["content"],
                                max_tokens=available_tokens //
                                (len(messages) - 1),
                            ))
                print(
                    f"Truncated context to fit within {available_tokens} tokens"
                )
            else:
                raise Exception("Message too long even after truncation")

        print("\n=== Step 2: Sending Request to AI Model ===")
        start_time = time.time()

        if model_id == "claude":
            # Use Anthropic's client interface
            full_context = "\n\n".join(msg["content"] for msg in messages)
            response = client.messages.create(
                model=model_config["models"]["code"],
                messages=[{
                    "role":
                    "user",
                    "content":
                    f"{full_context}\n\nPlease provide your response in valid JSON format following the structure specified above.",
                }],
                temperature=0.1,
                max_tokens=4096,
            )
            full_text = response.content[0].text
            print(f"\nResponse received in {time.time() - start_time:.1f}s")
            print(f"Response length: {len(full_text)} characters")
        elif model_id == "gemini":
            # Use the Google AI client
            try:
                model = client.GenerativeModel("gemini-2.0-flash-exp")
                chat = model.start_chat(history=[])

                # Combine all messages into a single context
                full_context = "\n\n".join(msg["content"] for msg in messages)

                response = chat.send_message(
                    full_context,
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.1,
                        candidate_count=1,
                        max_output_tokens=8192),
                )

                if not response or not response.text:
                    raise Exception("Empty response from Gemini")

                full_text = response.text.strip()
                print(
                    f"\nResponse received in {time.time() - start_time:.1f}s")
                print(f"Response length: {len(full_text)} characters")

            except Exception as e:
                error_msg = str(e)
                if "maximum context length" in error_msg.lower():
                    # Try again with more aggressive truncation
                    for i in range(len(messages) - 1):
                        if messages[i]["role"] == "system":
                            messages[i]["content"] = (
                                workspace_manager.
                                _truncate_content_for_context(
                                    messages[i]["content"],
                                    max_tokens=10000,  # Even more conservative
                                ))
                    # Combine truncated messages
                    full_context = "\n\n".join(msg["content"]
                                               for msg in messages)
                    response = chat.send_message(
                        full_context,
                        generation_config=genai.types.GenerationConfig(
                            temperature=0.1,
                            candidate_count=1,
                            max_output_tokens=4096),
                    )
                    if not response or not response.text:
                        raise Exception(
                            "Empty response from Gemini after truncation")
                    full_text = response.text.strip()
                else:
                    raise
        else:
            # Use streaming for other OpenAI-compatible models
            response = client.chat.completions.create(
                model=model_config["models"]["code"],
                messages=messages,
                temperature=1 if model_id in ["o1", "o1-mini"] else 0.1,
                stream=True,
            )

            print("Request sent, waiting for response...")
            socketio.emit("status", {
                "message": "Receiving AI response...",
                "step": 2
            })

            # Process the streamed response
            full_text = ""
            chunk_count = 0
            last_update = time.time()
            update_interval = 0.5

            for chunk in response:
                if (chunk and hasattr(chunk.choices[0], "delta")
                        and hasattr(chunk.choices[0].delta, "content")):
                    content = chunk.choices[0].delta.content
                    if content is not None:
                        full_text += content
                        chunk_count += 1

                    current_time = time.time()
                    if current_time - last_update >= update_interval:
                        elapsed = current_time - start_time
                        tokens_per_second = chunk_count / elapsed if elapsed > 0 else 0
                        print(
                            f"\rReceived {chunk_count} chunks ({len(full_text)} chars) in {elapsed:.1f}s ({tokens_per_second:.1f} chunks/s)",
                            end="",
                        )
                        socketio.emit(
                            "status",
                            {
                                "message":
                                f"Receiving response... ({len(full_text)} characters)",
                                "step": 2,
                                "progress": {
                                    "chunks": chunk_count,
                                    "chars": len(full_text),
                                    "elapsed": elapsed,
                                    "rate": tokens_per_second,
                                },
                            },
                        )
                        last_update = current_time

            print(f"\nResponse complete in {time.time() - start_time:.1f}s")
            print(
                f"Total response size: {len(full_text)} characters in {chunk_count} chunks"
            )

        # Clean up the response text and try to extract JSON
        cleaned_text = full_text.strip()

        # Try to extract JSON from the response if it's wrapped in markdown
        # code blocks
        if cleaned_text.startswith("```") and cleaned_text.endswith("```"):
            # Remove the code block markers and any language identifier
            cleaned_text = (cleaned_text.split("\n", 1)[1]
                            if "\n" in cleaned_text else cleaned_text)
            cleaned_text = (cleaned_text.rsplit("\n", 1)[0]
                            if "\n" in cleaned_text else cleaned_text)
            cleaned_text = cleaned_text.strip("`").strip()
            if cleaned_text.startswith("json"):
                cleaned_text = cleaned_text[4:].strip()

        # Try to find JSON content within the response
        json_start = cleaned_text.find("{")
        json_end = cleaned_text.rfind("}")

        if json_start != -1 and json_end != -1 and json_start < json_end:
            try:
                # Extract the JSON part
                json_text = cleaned_text[json_start:json_end + 1]

                # Preprocess the JSON text to handle triple quotes
                def preprocess_json(text):
                    # Split the text into parts by finding all occurrences of
                    # triple quotes
                    parts = []
                    last_pos = 0
                    pos = text.find('"""')

                    while pos != -1:
                        # Add the text before the triple quotes
                        parts.append(text[last_pos:pos])

                        # Find the closing triple quotes
                        end_pos = text.find('"""', pos + 3)
                        if end_pos == -1:
                            # If no closing quotes found, treat the rest as
                            # normal text
                            parts.append(text[pos:])
                            break

                        # Get the content between triple quotes and escape it
                        content = text[pos + 3:end_pos]
                        escaped_content = content.replace('"', '\\"').replace(
                            "\n", "\\n")
                        parts.append(f'"{escaped_content}"')

                        last_pos = end_pos + 3
                        pos = text.find('"""', last_pos)

                    # Add any remaining text
                    if last_pos < len(text):
                        parts.append(text[last_pos:])

                    # Join parts and normalize quotes
                    result = "".join(parts)
                    # Replace curly quotes with straight quotes
                    result = result.replace('"', '"').replace('"', '"')
                    return result

                # Preprocess the JSON text and parse it
                processed_json = preprocess_json(json_text)
                result = json.loads(processed_json)

                if isinstance(result, dict) and "operations" in result:
                    return result

            except json.JSONDecodeError as e:
                print(f"JSON decode error: {str(e)}")
                print(f"JSON text: {json_text}")
                print(f"Processed JSON: {processed_json}")
                raise ValueError(
                    f"Invalid JSON format: {str(e)}. Please try again with a clearer prompt."
                )

        print(
            f"Could not find valid JSON in response: {cleaned_text[:200]}...")
        raise ValueError(
            "Could not get a valid JSON response. Please try again with a clearer prompt."
        )

    except Exception as e:
        socketio.emit("status", {"message": f"Error: {str(e)}", "step": -1})
        print(f"\nError getting code suggestion: {str(e)}")
        raise


@app.route("/workspace/import-folder", methods=["POST"])
def import_folder():
    try:
        data = request.get_json()
        source_path = data.get("path")

        if not source_path:
            return jsonify({"error": "Missing source path"}), 400

        # Use the folder name as the workspace ID
        workspace_id = os.path.basename(source_path)
        workspace_dir = os.path.join(WORKSPACE_ROOT, workspace_id)

        # Check if workspace already exists
        if os.path.exists(workspace_dir):
            return jsonify(
                {"error": "A workspace with this name already exists"}), 400

        # Create link based on platform
        if os.name == "nt":  # Windows
            import subprocess

            try:
                # Use mklink /J to create a directory junction (no admin
                # required)
                subprocess.run(
                    ["cmd", "/c", "mklink", "/J", workspace_dir, source_path],
                    check=True,
                )
            except subprocess.CalledProcessError as e:
                return (
                    jsonify({
                        "error":
                        f"Failed to create directory junction: {str(e)}"
                    }),
                    500,
                )
        else:  # Unix-like systems
            os.symlink(source_path, workspace_dir, target_is_directory=True)

        # Create a .imported flag file to mark this as an imported workspace
        with open(os.path.join(workspace_dir, ".imported"), "w") as f:
            json.dump(
                {
                    "source_path": source_path,
                    "imported_at": datetime.now().isoformat()
                },
                f,
            )

        # Get the workspace structure
        structure = get_workspace_structure(workspace_dir)

        return jsonify({
            "status": "success",
            "message": "Folder imported as workspace successfully",
            "workspace_id": workspace_id,
            "workspace_dir": workspace_dir,
            "structure": structure,
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/available-folders", methods=["GET"])
def list_available_folders():
    """List folders available for import from user's home directory"""
    try:
        # Get user's home directory
        home_dir = os.path.expanduser("~")
        path = request.args.get("path", home_dir)

        # Ensure the path is within home directory for security
        if not os.path.abspath(path).startswith(os.path.abspath(home_dir)):
            return jsonify(
                {"error": "Access denied: Path outside home directory"}), 403

        # Get parent path for navigation
        parent_path = os.path.dirname(path) if path != home_dir else None

        available_items = []
        try:
            for item in os.listdir(path):
                full_path = os.path.join(path, item)
                if os.path.isdir(full_path):
                    try:
                        stats = os.stat(full_path)
                        item_info = {
                            "name": item,
                            "path": full_path,
                            "type": "directory",
                            "modified": stats.st_mtime,
                            "is_navigable": True,
                        }
                        # Only calculate size and files count if this is a
                        # potential import target
                        if not item.startswith("."):
                            try:
                                item_info.update({
                                    "size":
                                    sum(
                                        os.path.getsize(
                                            os.path.join(dirpath, filename))
                                            for dirpath, dirnames, filenames in
                                            os.walk(full_path)
                                            for filename in filenames),
                                    "files":
                                    sum(
                                        len(files)
                                        for _, _, files in os.walk(full_path)),
                                    "is_importable":
                                    True,
                                })
                            except BaseException:
                                item_info.update({
                                    "size": 0,
                                    "files": 0,
                                    "is_importable": False
                                })
                        available_items.append(item_info)
                    except Exception as e:
                        print(f"Error processing folder {item}: {e}")
                        continue
        except PermissionError:
            return jsonify(
                {"error": "Permission denied accessing this directory"}), 403

        return jsonify({
            "status":
            "success",
            "current_path":
            path,
            "parent_path":
            parent_path,
            "items":
            sorted(
                available_items,
                key=lambda x: (
                    not x.get("is_importable", False),
                    x["name"].lower(),
                ),
            ),
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/workspace/rename_file", methods=["POST"])
def rename_file():
    """Rename a file within a workspace"""
    try:
        data = request.json
        workspace_dir = data.get("workspace_dir")
        old_path = data.get("old_path")
        new_path = data.get("new_path")

        if not all([workspace_dir, old_path, new_path]):
            return (
                jsonify({
                    "status": "error",
                    "message": "Missing required parameters"
                }),
                400,
            )

        # Ensure paths are within workspace
        old_full_path = os.path.abspath(os.path.join(workspace_dir, old_path))
        new_full_path = os.path.abspath(os.path.join(workspace_dir, new_path))

        if not all(
                p.startswith(os.path.abspath(workspace_dir))
                for p in [old_full_path, new_full_path]):
            return jsonify({
                "status": "error",
                "message": "Invalid file path"
            }), 400

        # Check if source exists and target doesn't
        if not os.path.exists(old_full_path):
            return jsonify({
                "status": "error",
                "message": "Source file not found"
            }), 404

        if os.path.exists(new_full_path):
            return (
                jsonify({
                    "status": "error",
                    "message": "Target file already exists"
                }),
                400,
            )

        # Create target directory if it doesn't exist
        os.makedirs(os.path.dirname(new_full_path), exist_ok=True)

        # Rename the file
        os.rename(old_full_path, new_full_path)

        return jsonify({
            "status": "success",
            "message": "File renamed successfully"
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


def get_operation_diff(operation, workspace_dir):
    """Generate a diff for a file operation"""
    try:
        file_path = os.path.join(workspace_dir, operation["path"])

        # Get current content
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                current_content = f.read()
        except BaseException:
            current_content = ""

        # For create operations
        if operation["type"] == "create_file":
            new_content = operation.get("content", "")

        # For edit operations
        elif operation["type"] == "edit_file":
            new_content = current_content
            for change in operation.get("changes", []):
                if "old" in change and "new" in change:
                    new_content = new_content.replace(change["old"],
                                                              change["new"])
            # Store the new content in the operation
            operation["content"] = new_content

        # Generate unified diff
        from difflib import unified_diff

        diff_lines = list(
            unified_diff(
                current_content.splitlines(keepends=True),
                new_content.splitlines(keepends=True),
                fromfile=f"a/{operation['path']}",
                tofile=f"b/{operation['path']}",
            ))

        return {
            "old_content":
            current_content,
            "new_content":
            new_content,
            "diff": ("".join(diff_lines) if diff_lines else
                     f"No changes detected in {operation['path']}"),
        }
    except Exception as e:
        print(f"Error generating diff for {operation['path']}: {str(e)}")
        return {
            "old_content": "",
            "new_content": "",
            "diff": f"Error generating diff: {str(e)}",
        }


if __name__ == "__main__":
    # Run with eventlet server
    socketio.run(app, debug=False, host="0.0.0.0", port=5000)
