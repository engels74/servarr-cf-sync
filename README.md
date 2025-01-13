# Custom Format Sync for Radarr and Sonarr

<p align="center">
  <img src="https://i.imgur.com/T64BX5b.png" alt="Servarr Custom Format Sync" style="width: 35%;"/>
</p>

<p align="center">
  <a href="https://github.com/engels74/servarr-cf-sync/blob/main/LICENSE"><img src="https://img.shields.io/github/license/engels74/servarr-cf-sync"></a>
  <a href="https://github.com/engels74/servarr-cf-sync/stargazers"><img src="https://img.shields.io/github/stars/engels74/servarr-cf-sync.svg" alt="GitHub Stars"></a>
  <a href="https://endsoftwarepatents.org/innovating-without-patents"><img style="height: 20px;" src="https://static.fsf.org/nosvn/esp/logos/patent-free.svg"></a>
</p>

This project provides a GitHub Actions workflow to automatically sync custom formats across multiple Radarr and Sonarr instances, ensuring consistency in your media management setup.

## ✨ Key Features

- Sync custom formats to multiple Radarr and Sonarr instances
- Control which instances receive each custom format
- Set custom format scores for each quality profile
- Version tracking to ensure only updated formats are synced
- Automated syncing using GitHub Actions

## 📋 Custom Format Template

A `_template.json` file is provided in the `custom_formats/` directory to help you create your own custom formats. The template includes:

- Required and optional fields with documentation
- Version handling using `cfSync_version` for automatic updates
- Instance targeting options (`cfSync_radarr`, `cfSync_sonarr`, `cfSync_instances`)
- Score management with `cfSync_score`
- Example specification structure

Simply copy `_template.json`, rename it, and modify according to your needs. The version in `version.json` will be automatically updated based on your custom format's `cfSync_version`.

## 🚀 Quick Start

1. Fork this repository (use the [template-fork](https://github.com/engels74/servarr-cf-sync/tree/template-fork) branch)
2. Set up GitHub Secrets for your Radarr and Sonarr instances
3. Enable GitHub Actions for your repository
4. Customize your custom formats in the `custom_formats/` directory

For detailed instructions, please refer to our [Wiki](../../wiki).

## 📚 Documentation

- [Setup Guide](../../wiki/01.-Setup)
- [Configuration](../../wiki/02.-Configuration)
- [Usage Instructions](../../wiki/03.-Usage)
- [Troubleshooting](../../wiki/04.-Troubleshooting)

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## ⚖️ License

[![GNU AGPLv3 Image](https://www.gnu.org/graphics/agplv3-155x51.png)](https://www.gnu.org/licenses/agpl-3.0.en.html)

This project is licensed under the AGPLv3 License - see the LICENSE file for details.
