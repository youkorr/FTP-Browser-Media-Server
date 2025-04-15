# FTP Browser & Media Server for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

This integration adds FTP browsing, streaming and sharing capabilities to Home Assistant.

## Features

- Browse FTP servers directly from your Home Assistant UI
- Stream media files (images, music, videos) through Home Assistant
- Create temporary shareable links for files
- Track file count and total size with sensors
- Compatible with Home Assistant media browser
- Custom Lovelace card for easy file management

## Installation

1. Add this repository to HACS as a custom integration repository
2. Install the "FTP Browser & Media Server" integration through HACS
3. Restart Home Assistant
4. Go to Settings > Devices & Services and add the integration
5. Configure your FTP server details

## Lovelace Card

To use the custom card, add this to your Lovelace configuration:

resources:
  - url: /hacsfiles/ftp_browser/lovelace/ftp-browser-card.js
    type: module
