# LisztServ

LisztServ is a modern desktop application that helps you discover and create Spotify playlists from web content. It uses both direct URL scanning and AI-powered content analysis to find and organize music into playlists.

## Features

- 🎵 Scan web pages for Spotify album links
- 🤖 AI-powered music content extraction
- 📝 Create Spotify playlists automatically
- 🎨 Modern, user-friendly interface
- 🔄 Support for various music review sites and blogs

## Prerequisites

- Python 3.8 or higher
- Spotify Developer Account
- OpenAI API Key (for AI-powered scanning)
- Git (for cloning the repository)

## Quick Start

1. **Clone the Repository**
   ```bash
   git clone https://github.com/88dreams/lisztserv.git
   cd lisztserv
   ```

2. **Create and Activate Virtual Environment**
   ```bash
   # Windows
   python -m venv virtual
   .\virtual\Scripts\activate

   # macOS/Linux
   python3 -m venv virtual
   source virtual/bin/activate
   ```

3. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Environment Variables**
   Copy `.env.example` to `.env` and update with your credentials:
   ```
   SPOTIFY_CLIENT_ID=your_spotify_client_id
   SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
   SPOTIFY_REDIRECT_URI=http://localhost:8888/callback
   OPENAI_API_KEY=your_openai_api_key
   ```

5. **Run the Application**
   ```bash
   python -m lisztserv
   ```

## Documentation

- For detailed usage instructions, see the [Usage Guide](MASTER_DOCUMENTATION.md#usage-guide)
- For development setup, see the [Development Guide](MASTER_DOCUMENTATION.md#development-guidelines)
- For troubleshooting, see the [Troubleshooting Guide](MASTER_DOCUMENTATION.md#troubleshooting)
- For system architecture and API documentation, see [MASTER_DOCUMENTATION.md](MASTER_DOCUMENTATION.md)

## Contributing

Contributions are welcome! Please read our [Contributing Guidelines](CONTRIBUTING.md) for details on our code of conduct and the process for submitting pull requests.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Built with [Spotipy](https://spotipy.readthedocs.io/)
- UI powered by [Flask](https://flask.palletsprojects.com/) and [pywebview](https://pywebview.flowrl.com/)
- AI features powered by [OpenAI](https://openai.com/)
   

