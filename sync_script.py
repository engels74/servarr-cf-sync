import json
import logging
import os
import requests
import semver
import sys
from typing import Dict, List, Tuple

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Manages version information for custom formats
class VersionManager:
    def __init__(self, version_file: str = 'version.json'):
        self.version_file = version_file
        self.versions = self.load_versions()

    def load_versions(self) -> Dict[str, semver.VersionInfo]:
        if not os.path.exists(self.version_file):
            logging.info(f"No {self.version_file} found, starting fresh")
            return {}
            
        try:
            with open(self.version_file, 'r') as f:
                version_data = json.load(f)
                return {k: semver.VersionInfo.parse(v) for k, v in version_data.items()}
        except json.JSONDecodeError:
            logging.warning(f"Malformed {self.version_file}, starting fresh")
            return {}
        except Exception as e:
            logging.error(f"Error loading versions: {str(e)}")
            return {}

    def save_versions(self):
        try:
            with open(self.version_file, 'w') as f:
                json.dump({k: str(v) for k, v in self.versions.items()}, f, indent=4)
        except Exception as e:
            logging.error(f"Error saving versions: {str(e)}")
            raise

    def cleanup_versions(self, existing_files: List[str]):
        removed = set(self.versions.keys()) - set(existing_files)
        if removed:
            logging.info(f"Removing versions for non-existent files: {', '.join(removed)}")
            self.versions = {k: v for k, v in self.versions.items() if k in existing_files}
            self.save_versions()

    def update_version(self, filename: str, new_version: semver.VersionInfo):
        self.versions[filename] = new_version
        self.save_versions()

# Handles API communication with Radarr/Sonarr instances
class APIClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({'X-Api-Key': self.api_key})

    # Retrieves all custom formats from the instance
    def get_custom_formats(self) -> List[Dict]:
        try:
            response = self.session.get(f'{self.base_url}/api/v3/customformat')
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logging.error(f"Error fetching custom formats: {e}")
            logging.error(f"Response content: {response.text if 'response' in locals() else 'No response'}")
            raise

    # Updates an existing custom format or creates a new one
    def update_custom_format(self, custom_format: Dict) -> Dict:
        try:
            # Determine if we're updating an existing format or creating a new one
            if 'id' in custom_format:
                url = f'{self.base_url}/api/v3/customformat/{custom_format["id"]}'
                response = self.session.put(url, json=custom_format)
            else:
                url = f'{self.base_url}/api/v3/customformat'
                response = self.session.post(url, json=custom_format)

            logging.debug(f"Payload being sent: {json.dumps(custom_format, indent=2)}")
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logging.error(f"Error updating custom format: {e}")
            logging.error(f"Response status code: {response.status_code if 'response' in locals() else 'No response'}")
            logging.error(f"Response content: {response.text if 'response' in locals() else 'No response'}")
            raise

    # Retrieves all quality profiles from the instance
    def get_quality_profiles(self) -> List[Dict]:
        try:
            response = self.session.get(f'{self.base_url}/api/v3/qualityprofile')
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logging.error(f"Error fetching quality profiles: {e}")
            raise

    # Updates a specific quality profile
    def update_quality_profile(self, profile: Dict) -> Dict:
        try:
            url = f'{self.base_url}/api/v3/qualityprofile/{profile["id"]}'
            response = self.session.put(url, json=profile)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logging.error(f"Error updating quality profile: {e}")
            raise

# Manages the synchronization of custom formats
class CustomFormatSyncer:
    def __init__(self, custom_formats_dir: str):
        self.custom_formats_dir = custom_formats_dir
        self.version_manager = VersionManager()

    # Loads all custom format JSON files from the specified directory
    def load_custom_formats(self) -> Dict[str, Dict]:
        custom_formats = {}
        try:
            for filename in os.listdir(self.custom_formats_dir):
                if filename.endswith('.json'):
                    with open(os.path.join(self.custom_formats_dir, filename), 'r') as f:
                        custom_formats[filename] = json.load(f)
            return custom_formats
        except json.JSONDecodeError as e:
            logging.error(f"Error parsing custom format file {filename}: {str(e)}")
            raise
        except Exception as e:
            logging.error(f"Error loading custom formats: {str(e)}")
            raise

    def sync_custom_formats(self, instances: List[Tuple[str, str, str]]):
        try:
            custom_formats = self.load_custom_formats()
            if not custom_formats:
                logging.warning("No custom formats found to sync")
                return

            # Clean up versions for non-existent files
            self.version_manager.cleanup_versions(list(custom_formats.keys()))
            
            # Find the latest version across all formats
            latest_version = semver.VersionInfo.parse('0.0.0')
            for filename, format_data in custom_formats.items():
                if filename == '_template.json':
                    continue
                try:
                    version = semver.VersionInfo.parse(format_data.get('cfSync_version', '0.0.0'))
                    if version > latest_version:
                        latest_version = version
                except ValueError as e:
                    logging.error(f"Invalid version in {filename}: {str(e)}")
                    continue
            
            for filename, format_data in custom_formats.items():
                try:
                    # Skip template file
                    if filename == '_template.json':
                        logging.info("Skipping _template.json")
                        continue

                    file_version = semver.VersionInfo.parse(format_data.get('cfSync_version', '0.0.0'))
                    stored_version = self.version_manager.versions.get(filename, semver.VersionInfo.parse('0.0.0'))

                    # Sync if:
                    # 1. File version is newer than stored version
                    # 2. File version is behind latest version (needs alignment)
                    if file_version > stored_version or file_version < latest_version:
                        if file_version < latest_version:
                            logging.warning(f"{filename} version {file_version} is behind latest version {latest_version}")
                        
                        for instance_name, url, api_key in instances:
                            if not self.should_sync_to_instance(format_data, instance_name):
                                logging.info(f"Skipping {filename} for {instance_name} based on cfSync settings")
                                continue

                            client = APIClient(url, api_key)
                            try:
                                existing_formats = client.get_custom_formats()
                                formatted_custom_format = self.prepare_format_for_sync(format_data)
                                synced_format = self.sync_format(client, existing_formats, formatted_custom_format)
                                
                                if synced_format and 'cfSync_score' in format_data:
                                    self.sync_format_score(client, synced_format, format_data['cfSync_score'])
                                
                                logging.info(f"Synced {filename} to {instance_name}")
                            except requests.RequestException as e:
                                logging.error(f"Error syncing {filename} to {instance_name}: {str(e)}")
                                continue
                        
                        self.version_manager.update_version(filename, file_version)
                        logging.info(f"Updated {filename} to version {file_version}")
                    else:
                        logging.info(f"No updates needed for {filename} (current: {file_version})")

                except ValueError as e:
                    logging.error(f"Invalid version format in {filename}: {str(e)}")
                    continue
                except Exception as e:
                    logging.error(f"Error processing {filename}: {str(e)}")
                    continue

        except Exception as e:
            logging.error(f"An error occurred during sync process: {str(e)}")
            raise

    # Determines if a custom format should be synced to a specific instance
    def should_sync_to_instance(self, format_data: Dict, instance_name: str) -> bool:
        if 'cfSync_instances' in format_data:
            # Extract the instance number (e.g., "003" from "Radarr_003")
            instance_number = instance_name.split('_')[-1]
            return instance_name in format_data['cfSync_instances'] or instance_number in format_data['cfSync_instances']
        else:
            # Determine if it's a Radarr or Sonarr instance
            instance_type = 'radarr' if 'Radarr' in instance_name else 'sonarr'
            return format_data.get(f'cfSync_{instance_type}', True)

    # Prepares a custom format for syncing by extracting relevant fields
    def prepare_format_for_sync(self, format_data: Dict) -> Dict:
        # Extract only the necessary fields for syncing
        return {
            "name": format_data.get("name"),
            "includeCustomFormatWhenRenaming": format_data.get("includeCustomFormatWhenRenaming", False),
            "specifications": format_data.get("specifications", [])
        }

    # Syncs a single custom format to an instance
    def sync_format(self, client: APIClient, existing_formats: List[Dict], new_format: Dict) -> Dict:
        existing_format = next((f for f in existing_formats if f['name'] == new_format['name']), None)
        
        # Ensure correct format for specifications
        for spec in new_format.get('specifications', []):
            if isinstance(spec.get('fields'), dict):
                spec['fields'] = [{"name": "value", "value": spec['fields']['value']}]
            elif isinstance(spec.get('fields'), list):
                spec['fields'] = [
                    {"name": field.get('name', 'value'), "value": field.get('value')} if isinstance(field, dict) else field
                    for field in spec['fields']
                ]
            else:
                logging.error(f"Invalid fields format for specification: {spec}")
                return None
        
        logging.info(f"Attempting to sync custom format: {json.dumps(new_format, indent=2)}")

        try:
            if existing_format:
                new_format['id'] = existing_format['id']
                if new_format != existing_format:
                    updated_format = client.update_custom_format(new_format)
                    logging.info(f"Updated custom format: {updated_format['name']}")
                    return updated_format
            else:
                created_format = client.update_custom_format(new_format)
                logging.info(f"Created new custom format: {created_format['name']}")
                return created_format
        except requests.RequestException as e:
            logging.error(f"Failed to sync custom format {new_format['name']}: {str(e)}")
            raise
        
        return None

    # Updates the score of a custom format in all quality profiles
    def sync_format_score(self, client: APIClient, custom_format: Dict, score: int):
        try:
            profiles = client.get_quality_profiles()
            for profile in profiles:
                updated = False
                for format_item in profile.get('formatItems', []):
                    if format_item['format'] == custom_format['id']:
                        if format_item['score'] != score:
                            format_item['score'] = score
                            updated = True
                
                if updated:
                    client.update_quality_profile(profile)
                    logging.info(f"Updated score for {custom_format['name']} in profile {profile['name']}")
        
        except requests.RequestException as e:
            logging.error(f"Error syncing format score: {str(e)}")
            raise

# Main execution function
def main():
    custom_formats_dir = 'custom_formats'
    
    instances = []
    
    # Dynamically load Radarr instances
    radarr_count = 1
    while True:
        url = os.environ.get(f'RADARR_{radarr_count:03d}_URL')
        api_key = os.environ.get(f'RADARR_{radarr_count:03d}_API_KEY')
        if not url or not api_key:
            break
        instances.append((f'Radarr_{radarr_count:03d}', url, api_key))
        radarr_count += 1
    
    # Dynamically load Sonarr instances
    sonarr_count = 1
    while True:
        url = os.environ.get(f'SONARR_{sonarr_count:03d}_URL')
        api_key = os.environ.get(f'SONARR_{sonarr_count:03d}_API_KEY')
        if not url or not api_key:
            break
        instances.append((f'Sonarr_{sonarr_count:03d}', url, api_key))
        sonarr_count += 1
    
    # Debugging statements to ensure environment variables are correctly parsed
    for instance in instances:
        logging.info(f"{instance[0]} URL: {instance[1]}")
    
    if not instances:
        logging.error("No Radarr or Sonarr instances configured. Please check your environment variables.")
        sys.exit(1)

    syncer = CustomFormatSyncer(custom_formats_dir)
    try:
        syncer.sync_custom_formats(instances)
    except Exception as e:
        logging.error(f"An error occurred during sync: {str(e)}")
        sys.exit(1)  # Exit with non-zero status on error

if __name__ == '__main__':
    main()
