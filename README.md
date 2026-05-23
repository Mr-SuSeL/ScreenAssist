# ScreenAssist

**ScreenerAssist** is a modular, high-performance desktop companion designed to provide real-time AI-driven analysis of your screen content. It uses a clean, threaded architecture to capture and analyze specific screen areas, making it an ideal tool for rapid technical task evaluation and workflow assistance.

## Key Features
*   **Real-time Analysis:** Captures and processes screen segments via a global hotkey (`F8`).
*   **Modular Architecture:** Separates screen capture, API communication, and UI for maintainability.
*   **Multi-mode Support:** Easily switch between analysis modes (GIT, English, Code, etc.) using the overlay.
*   **Secure:** Built-in environment variable validation and git-ignore protection to keep your API keys safe.
*   **Always-on-top UI:** Minimalist `CustomTkinter` interface that stays visible during your workflow.

## Architecture
The application follows a clean, decoupled design:
*   **`core/`**: Contains the capture pipeline (`mss`), API engine (`VisionClient`), and prompt management logic.
*   **`ui/`**: Implements the `CustomTkinter` overlay for immediate visual feedback.
*   **`main.py`**: Orchestrates the multi-threaded hotkey listener and processing pipeline.

## Setup & Installation

### 1. Prerequisites
- Python 3.10+
- Administrative privileges (required by `keyboard` library for global hotkey handling).

### 2. Configuration
Clone the repository and set up your environment:

```bash
# Install dependencies
pip install -r requirements.txt

# Copy the example environment file
cp .env.example .env