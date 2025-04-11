import json
import logging
import os
import requests
import semver
import sys
from typing import TypedDict, cast, NotRequired, Literal

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Type definitions
class FormatItem(TypedDict):
    format: int
    score: int

class QualityProfile(TypedDict):
    id: int
    name: str
    formatItems: list[FormatItem]

# Define more specific types for specifications
class Field(TypedDict):
    name: str
    value: str

class Specification(TypedDict):
    name: str
    implementation: str
    negate: bool
    required: bool
    fields: list[Field]

class CustomFormat(TypedDict):
    id: int
    name: str
    includeCustomFormatWhenRenaming: NotRequired[bool]
    specifications: NotRequired[list[Specification]]

class FormatData(TypedDict, total=False):
    name: str
    includeCustomFormatWhenRenaming: bool
    specifications: list[Specification]
    cfSync_version: str
    cfSync_score: int
    cfSync_instances: list[str]
    cfSync_radarr: bool
    cfSync_sonarr: bool

# We need a dictionary class that can handle the format data for API interactions
class FormatDict(dict[str, object]):
    pass

# Manages version information for custom formats
class VersionManager:
    def __init__(self, version_file: str = 'version.json'):
        self.version_file: str = version_file
        self.versions: dict[str, semver.VersionInfo] = self.load_versions()

    def load_versions(self) -> dict[str, semver.VersionInfo]:
        if not os.path.exists(self.version_file):
            logging.info(f"No {self.version_file} found, starting fresh")
            return {}
            
        try:
            with open(self.version_file, 'r') as f:
                # Read version data as dict[str, str]
                version_data: dict[str, str] = json.load(f)
                result: dict[str, semver.VersionInfo] = {}
                # Convert string values to VersionInfo objects
                for k, v in version_data.items():
                    result[k] = semver.VersionInfo.parse(v)
                return result
        except json.JSONDecodeError:
            logging.warning(f"Malformed {self.version_file}, starting fresh")
            return {}
        except Exception as e:
            logging.error(f"Error loading versions: {str(e)}")
            return {}

    def save_versions(self) -> None:
        try:
            with open(self.version_file, 'w') as f:
                json.dump({k: str(v) for k, v in self.versions.items()}, f, indent=4)
        except Exception as e:
            logging.error(f"Error saving versions: {str(e)}")
            raise

    def cleanup_versions(self, existing_files: list[str]) -> None:
        removed = set(self.versions.keys()) - set(existing_files)
        if removed:
            logging.info(f"Removing versions for non-existent files: {', '.join(removed)}")
            self.versions = {k: v for k, v in self.versions.items() if k in existing_files}
            self.save_versions()

    def update_version(self, filename: str, new_version: semver.VersionInfo) -> None:
        self.versions[filename] = new_version
        self.save_versions()

# Handles API communication with Radarr/Sonarr instances
class APIClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url: str = base_url
        self.api_key: str = api_key
        self.session: requests.Session = requests.Session()
        self.session.headers.update({'X-Api-Key': self.api_key})

    # Retrieves all custom formats from the instance
    def get_custom_formats(self) -> list[CustomFormat]:
        response: requests.Response | None = None
        try:
            response = self.session.get(f'{self.base_url}/api/v3/customformat')
            response.raise_for_status()
            return cast(list[CustomFormat], response.json())
        except requests.RequestException as e:
            logging.error(f"Error fetching custom formats: {e}")
            logging.error(f"Response content: {response.text if response else 'No response'}")
            raise

    # Updates an existing custom format or creates a new one
    def update_custom_format(self, custom_format: FormatDict) -> CustomFormat:
        response: requests.Response | None = None
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
            return cast(CustomFormat, response.json())
        except requests.RequestException as e:
            logging.error(f"Error updating custom format: {e}")
            logging.error(f"Response status code: {response.status_code if response else 'No response'}")
            logging.error(f"Response content: {response.text if response else 'No response'}")
            raise

    # Retrieves all quality profiles from the instance
    def get_quality_profiles(self) -> list[QualityProfile]:
        try:
            response = self.session.get(f'{self.base_url}/api/v3/qualityprofile')
            response.raise_for_status()
            return cast(list[QualityProfile], response.json())
        except requests.RequestException as e:
            logging.error(f"Error fetching quality profiles: {e}")
            raise

    # Updates a specific quality profile
    def update_quality_profile(self, profile: QualityProfile) -> QualityProfile:
        try:
            url = f'{self.base_url}/api/v3/qualityprofile/{profile["id"]}'
            response = self.session.put(url, json=profile)
            response.raise_for_status()
            return cast(QualityProfile, response.json())
        except requests.RequestException as e:
            logging.error(f"Error updating quality profile: {e}")
            raise

# Manages the synchronization of custom formats
class CustomFormatSyncer:
    def __init__(self, custom_formats_dir: str):
        self.custom_formats_dir: str = custom_formats_dir
        self.version_manager: VersionManager = VersionManager()

    # Loads all custom format JSON files from the specified directory
    def load_custom_formats(self) -> dict[str, FormatData]:
        custom_formats: dict[str, FormatData] = {}
        current_filename = ""
        try:
            for filename in os.listdir(self.custom_formats_dir):
                current_filename = filename
                if filename.endswith('.json'):
                    with open(os.path.join(self.custom_formats_dir, filename), 'r') as f:
                        format_data = cast(FormatData, json.load(f))
                        custom_formats[filename] = format_data
            return custom_formats
        except json.JSONDecodeError as e:
            logging.error(f"Error parsing custom format file {current_filename}: {str(e)}")
            raise
        except Exception as e:
            logging.error(f"Error loading custom formats: {str(e)}")
            raise

    def sync_custom_formats(self, instances: list[tuple[str, str, str]]) -> None:
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
                    version_str = format_data.get('cfSync_version', '0.0.0')
                    version = semver.VersionInfo.parse(version_str)
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

                    version_str = format_data.get('cfSync_version', '0.0.0')
                    file_version = semver.VersionInfo.parse(version_str)
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
                                    score = format_data['cfSync_score']
                                    self.sync_format_score(client, synced_format, score)
                                
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
    def should_sync_to_instance(self, format_data: FormatData, instance_name: str) -> bool:
        if 'cfSync_instances' in format_data:
            # Extract the instance number (e.g., "003" from "Radarr_003")
            instance_number = instance_name.split('_')[-1]
            instances = format_data.get('cfSync_instances', [])
            return instance_name in instances or instance_number in instances
        else:
            # Determine if it's a Radarr or Sonarr instance
            instance_type: Literal['radarr', 'sonarr'] = 'radarr' if 'Radarr' in instance_name else 'sonarr'
            return format_data.get(f'cfSync_{instance_type}', True)

    # Prepares a custom format for syncing by extracting relevant fields
    def prepare_format_for_sync(self, format_data: FormatData) -> FormatDict:
        # Extract only the necessary fields for syncing
        result = FormatDict()
        result["name"] = format_data.get("name", "")
        result["includeCustomFormatWhenRenaming"] = format_data.get("includeCustomFormatWhenRenaming", False)
        
        # Explicitly handle specifications to avoid type issues
        if "specifications" in format_data:
            result["specifications"] = format_data["specifications"]
            
        return result

    # Syncs a single custom format to an instance
    def sync_format(self, client: APIClient, existing_formats: list[CustomFormat], new_format: FormatDict) -> CustomFormat | None:
        existing_format = next((f for f in existing_formats if f.get('name') == new_format.get('name')), None)
        
        # Ensure correct format for specifications
        if "specifications" in new_format:
            specs_obj = new_format["specifications"]
            if isinstance(specs_obj, list):
                for spec_dict in specs_obj:
                    if not isinstance(spec_dict, dict):
                        continue
                        
                    if "fields" in spec_dict:
                        fields_obj = spec_dict["fields"]
                        if isinstance(fields_obj, dict):
                            # Convert dict fields to list format
                            field_value = str(fields_obj.get("value", ""))
                            spec_dict["fields"] = [{"name": "value", "value": field_value}]
                        elif isinstance(fields_obj, list):
                            # Process list of fields
                            field_list: list[dict[str, str]] = []
                            for field_obj in fields_obj:
                                if isinstance(field_obj, dict):
                                    name = str(field_obj.get("name", "value"))
                                    value = str(field_obj.get("value", ""))
                                    field_list.append({"name": name, "value": value})
                                # Skip non-dict fields to prevent type errors
                            spec_dict["fields"] = field_list
                        else:
                            logging.error(f"Invalid fields format for specification: {spec_dict}")
                            return None
        
        logging.info(f"Attempting to sync custom format: {json.dumps(new_format, indent=2)}")

        try:
            if existing_format:
                new_format['id'] = existing_format['id']
                if new_format != existing_format:
                    updated_format = client.update_custom_format(new_format)
                    logging.info(f"Updated custom format: {updated_format['name']}")
                    return updated_format
                return existing_format
            else:
                created_format = client.update_custom_format(new_format)
                logging.info(f"Created new custom format: {created_format['name']}")
                return created_format
        except requests.RequestException as e:
            logging.error(f"Failed to sync custom format {new_format.get('name', '')}: {str(e)}")
            raise

    # Updates the score of a custom format in all quality profiles
    def sync_format_score(self, client: APIClient, custom_format: CustomFormat, score: int) -> None:
        try:
            profiles = client.get_quality_profiles()
            for profile in profiles:
                updated = False
                format_id = custom_format['id']  # id is required in CustomFormat now
                    
                for format_item in profile.get('formatItems', []):
                    if format_item['format'] == format_id:
                        if format_item['score'] != score:
                            format_item['score'] = score
                            updated = True
                
                if updated:
                    updated_profile = client.update_quality_profile(profile)
                    format_name = custom_format['name']  # name is required in CustomFormat now
                    logging.info(f"Updated score for {format_name} in profile {updated_profile['name']}")
        
        except requests.RequestException as e:
            logging.error(f"Error syncing format score: {str(e)}")
            raise

# Main execution function
def main() -> None:
    custom_formats_dir = 'custom_formats'
    
    instances: list[tuple[str, str, str]] = []
    
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
