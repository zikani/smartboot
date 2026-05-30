# Contributing to SmartBoot

Thank you for your interest in contributing to SmartBoot! This document provides guidelines and instructions for contributing to the project.

## Code of Conduct

- Be respectful and inclusive
- Provide constructive feedback
- Focus on what is best for the community
- Show empathy towards other community members

## Getting Started

### Prerequisites

- Python 3.7 or higher
- Git
- PyQt5 (see requirements.txt)

### Setting Up Development Environment

1. Fork the repository on GitHub
2. Clone your fork:
   ```bash
   git clone https://github.com/YOUR_USERNAME/smartboot.git
   cd smartboot
   ```

3. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

5. Create a new branch for your feature:
   ```bash
   git checkout -b feature/your-feature-name
   ```

## Development Guidelines

### Code Style

- Follow PEP 8 style guidelines
- Use meaningful variable and function names
- Add docstrings to all functions and classes
- Keep functions focused and modular
- Maximum line length: 100 characters

### Commit Messages

Use clear and descriptive commit messages:

```
feat: add support for UEFI boot mode
fix: resolve device detection issue on Linux
docs: update installation instructions
test: add unit tests for USB manager
```

### Testing

- Write unit tests for new features
- Test on multiple platforms (Windows, Linux, macOS) if possible
- Ensure existing tests pass before submitting

## Project Structure

```
smartboot/
├── core/
│   ├── boot_sector/       # Boot sector writing logic
│   ├── disk_formatter.py  # Disk formatting operations
│   ├── image_writer.py    # ISO/image writing
│   ├── iso_manager.py     # ISO file operations
│   └── usb_manager.py     # USB device detection
├── gui/
│   └── main_window.py     # Main GUI window
├── utils/
│   └── logger.py          # Logging utilities
├── docs/                  # Documentation
├── tests/                 # Test files
└── main.py               # Application entry point
```

## Submitting Changes

### Pull Request Process

1. Ensure your code follows the project guidelines
2. Update documentation if needed
3. Add tests for new features
4. Commit your changes with clear messages
5. Push to your fork
6. Create a pull request with:
   - Clear title and description
   - Reference related issues
   - Screenshots for UI changes (if applicable)

### Pull Request Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
Describe how you tested your changes

## Checklist
- [ ] Code follows project style guidelines
- [ ] Tests added/updated
- [ ] Documentation updated
- [ ] No new warnings generated
```

## Reporting Issues

When reporting bugs, please include:

- Operating system and version
- Python version
- Steps to reproduce
- Expected behavior
- Actual behavior
- Error messages or logs

## Feature Requests

For feature requests:

- Describe the use case
- Explain why it would be beneficial
- Suggest possible implementation approaches
- Consider if it fits the project scope

## Questions

Feel free to open an issue for questions about:
- Implementation details
- Design decisions
- Best practices
- Troubleshooting

## License

By contributing to SmartBoot, you agree that your contributions will be licensed under the MIT License.

## Acknowledgments

Thank you for contributing to SmartBoot! Your contributions help make this project better for everyone.
