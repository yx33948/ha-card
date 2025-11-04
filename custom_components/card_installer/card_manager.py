"""Card Manager for downloading and installing cards."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Any

import aiofiles
import aiohttp
from aiofiles.os import makedirs

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class CardManager:
    """Manages card installation and updates."""

    def __init__(
        self,
        hass: HomeAssistant,
        repo_url: str,
        branch: str = "master",
        auto_update: bool = True,
        update_interval: int = 3600,
    ) -> None:
        """Initialize Card Manager."""
        self.hass = hass
        self.repo_url = repo_url.rstrip("/")
        self.branch = branch
        self.auto_update = auto_update
        self.update_interval = update_interval
        self._auto_update_task: asyncio.Task | None = None

        # Determine base paths
        self.config_dir = Path(hass.config.config_dir)
        self.www_dir = self.config_dir / "www"
        self.community_dir = self.www_dir / "community"
        self.storage_dir = self.config_dir / ".storage"
        self.resources_file = self.storage_dir / "lovelace_resources"

        # Determine repository type and base URL
        if "gitee.com" in self.repo_url:
            self.repo_type = "gitee"
            # Extract repo path: remove protocol, domain, .git suffix, and trailing slashes
            repo_path = re.sub(r"https?://gitee\.com/", "", self.repo_url)
            repo_path = repo_path.rstrip("/")
            # Remove .git suffix if present
            if repo_path.endswith(".git"):
                repo_path = repo_path[:-4]
            # Remove any path segments after owner/repo (e.g., /tree/master)
            repo_path = "/".join(repo_path.split("/")[:2])
            self.raw_base_url = f"https://gitee.com/{repo_path}/raw/{self.branch}"
            self.api_base_url = f"https://gitee.com/api/v5/repos/{repo_path}"
            _LOGGER.debug("Gitee repo path: %s, API URL: %s", repo_path, self.api_base_url)
        elif "github.com" in self.repo_url:
            self.repo_type = "github"
            # Extract repo path: remove protocol, domain, .git suffix, and trailing slashes
            repo_path = re.sub(r"https?://github\.com/", "", self.repo_url)
            repo_path = repo_path.rstrip("/")
            # Remove .git suffix if present
            if repo_path.endswith(".git"):
                repo_path = repo_path[:-4]
            # Remove any path segments after owner/repo (e.g., /tree/master)
            repo_path = "/".join(repo_path.split("/")[:2])
            self.raw_base_url = f"https://raw.githubusercontent.com/{repo_path}/{self.branch}"
            self.api_base_url = f"https://api.github.com/repos/{repo_path}"
            _LOGGER.debug("GitHub repo path: %s, API URL: %s", repo_path, self.api_base_url)
        else:
            raise ValueError(f"Unsupported repository URL: {self.repo_url}")

    async def async_setup(self) -> None:
        """Set up directories and resources file."""
        # Create directories
        await makedirs(self.community_dir, exist_ok=True)
        await makedirs(self.storage_dir, exist_ok=True)

        # Initialize resources file if it doesn't exist
        if not await self._file_exists(self.resources_file):
            await self._init_resources_file()

    async def _process_single_card(self, filename: str, existing_resources: set[str], semaphore: asyncio.Semaphore) -> tuple[str, bool, bool]:
        """Process a single card file (download and add to resources).
        
        Returns: (filename, success, is_new_installation)
        """
        async with semaphore:  # Limit concurrent downloads
            resource_url = f"/hacsfiles/{filename}"
            is_new = resource_url not in existing_resources
            
            try:
                # Download file
                download_success = await self._download_file(filename)
                
                if not download_success:
                    return (filename, False, is_new)
                
                # If it's a new card, add to resources
                if is_new:
                    if await self._add_resource(resource_url):
                        return (filename, True, True)
                    else:
                        _LOGGER.error("Failed to add resource: %s", filename)
                        return (filename, False, True)
                else:
                    # Existing card, just updated the file
                    return (filename, True, False)
                    
            except Exception as err:
                _LOGGER.error("Error processing %s: %s", filename, err, exc_info=True)
                return (filename, False, is_new)

    async def async_install_cards(self, max_concurrent: int = 3) -> None:
        """Install cards from repository with concurrent downloads."""
        await self.async_setup()

        _LOGGER.info("Starting card installation from %s", self.repo_url)

        # Get list of JS files from repository
        js_files = await self._get_repo_files()

        if not js_files:
            _LOGGER.warning("No JS files found in repository")
            return

        _LOGGER.info("Found %d JS file(s) in repository", len(js_files))

        # Get existing resources
        existing_resources = await self._get_existing_resources()

        # Create semaphore to limit concurrent downloads
        semaphore = asyncio.Semaphore(max_concurrent)

        # Process all files concurrently (with semaphore limiting)
        tasks = [
            self._process_single_card(filename, existing_resources, semaphore)
            for filename in js_files
        ]

        # Wait for all tasks to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Count results
        installed_count = 0
        updated_count = 0
        error_count = 0

        for result in results:
            if isinstance(result, Exception):
                error_count += 1
                _LOGGER.error("Unexpected error processing card: %s", result, exc_info=True)
            else:
                filename, success, is_new = result
                if success:
                    if is_new:
                        installed_count += 1
                        _LOGGER.info("Successfully installed: %s", filename)
                    else:
                        updated_count += 1
                        _LOGGER.debug("Successfully updated: %s", filename)
                else:
                    error_count += 1
                    _LOGGER.error("Failed to process: %s", filename)

        _LOGGER.info(
            "Installation complete - Installed: %d, Updated: %d, Errors: %d",
            installed_count,
            updated_count,
            error_count,
        )

        if installed_count > 0:
            _LOGGER.warning(
                "Please restart Home Assistant for new cards to take effect!"
            )

    async def _find_all_js_files(self, directory: Path) -> list[Path]:
        """Recursively find all JS files in directory."""
        js_files = []
        try:
            if not directory.exists() or not directory.is_dir():
                return js_files
            
            # Walk through directory recursively
            for root, dirs, files in os.walk(directory):
                for file in files:
                    if file.endswith(".js") and not file.endswith(".min.js.map"):
                        file_path = Path(root) / file
                        # Only include files, not directories
                        if file_path.is_file():
                            js_files.append(file_path)
                            
        except Exception as err:
            _LOGGER.error("Error finding JS files in %s: %s", directory, err)
        
        return js_files

    async def async_add_local_cards_to_resources(self) -> None:
        """Add all local card files to Lovelace resources if not already added."""
        await self.async_setup()
        
        _LOGGER.info("Checking local card files and adding to resources...")
        
        # Get all JS files in community directory (recursively)
        if not await self._file_exists(self.community_dir):
            _LOGGER.warning("Community directory does not exist: %s", self.community_dir)
            return
        
        # Find all JS files recursively
        js_file_paths = await self._find_all_js_files(self.community_dir)
        
        if not js_file_paths:
            _LOGGER.info("No local card files found in %s", self.community_dir)
            return
        
        _LOGGER.info("Found %d JS file(s) in directory", len(js_file_paths))
        
        # Get existing resources (both URLs and full items)
        existing_resources_data = await self._get_existing_resources_data()
        existing_urls = {item.get("url", "") for item in existing_resources_data}
        
        added_count = 0
        skipped_count = 0
        migrated_count = 0
        error_count = 0
        
        for file_path in js_file_paths:
            try:
                # Get relative path from community_dir
                try:
                    relative_path = file_path.relative_to(self.community_dir)
                except ValueError:
                    # If file is not relative to community_dir, use just the filename
                    relative_path = Path(file_path.name)
                
                # Convert to forward slashes for URL (HACS uses /hacsfiles/)
                filename = str(relative_path).replace("\\", "/")
                
                new_resource_url = f"/hacsfiles/{filename}"
                old_resource_url = f"/local/community/{filename}"
                
                _LOGGER.debug("Processing file: %s -> %s", file_path, new_resource_url)
                
                # Check if new path already exists
                if new_resource_url in existing_urls:
                    _LOGGER.debug("Resource already exists with new path: %s", filename)
                    skipped_count += 1
                    continue
                
                # Check if old path exists and needs migration
                if old_resource_url in existing_urls:
                    _LOGGER.info("Migrating resource from %s to %s", old_resource_url, new_resource_url)
                    if await self._migrate_resource(old_resource_url, new_resource_url):
                        migrated_count += 1
                        _LOGGER.info("Migrated resource for: %s", filename)
                    else:
                        _LOGGER.error("Failed to migrate resource for: %s", filename)
                        # Try to add as new resource
                        if await self._add_resource(new_resource_url):
                            added_count += 1
                            _LOGGER.info("Added resource for local file: %s", filename)
                    continue
                
                # Add new resource
                if await self._add_resource(new_resource_url):
                    added_count += 1
                    _LOGGER.info("Added resource for local file: %s", filename)
                else:
                    error_count += 1
                    _LOGGER.error("Failed to add resource for: %s", filename)
                    
            except Exception as err:
                error_count += 1
                _LOGGER.error("Error processing file %s: %s", file_path, err, exc_info=True)
        
        _LOGGER.info(
            "Resource update complete - Added: %d, Migrated: %d, Already existed: %d, Errors: %d",
            added_count,
            migrated_count,
            skipped_count,
            error_count
        )
        
        if added_count > 0 or migrated_count > 0:
            _LOGGER.warning(
                "Please restart Home Assistant for new resources to take effect!"
            )

    async def async_update_cards(self) -> None:
        """Update existing cards from repository."""
        _LOGGER.info("Updating cards from %s", self.repo_url)

        js_files = await self._get_repo_files()

        if not js_files:
            _LOGGER.warning("No JS files found in repository")
            return

        updated_count = 0

        for filename in js_files:
            try:
                if await self._download_file(filename):
                    updated_count += 1
                    _LOGGER.info("Updated: %s", filename)
            except Exception as err:
                _LOGGER.error("Error updating %s: %s", filename, err)

        _LOGGER.info("Update complete - Updated %d file(s)", updated_count)

    async def async_remove_card(self, url: str | None = None, filename: str | None = None) -> None:
        """Remove a card from resources and delete the file."""
        if not url and not filename:
            _LOGGER.error("Either url or filename must be provided")
            return

        if filename:
            resource_url = f"/hacsfiles/{filename}"
        else:
            resource_url = url

        # Remove from resources
        await self._remove_resource(resource_url)

        # Delete file if filename is provided
        if filename:
            file_path = self.community_dir / filename
            if await self._file_exists(file_path):
                os.remove(file_path)
                _LOGGER.info("Deleted file: %s", filename)

        _LOGGER.info("Removed card: %s", resource_url)

    async def _get_repo_files(self) -> list[str]:
        """Get list of JS files from repository."""
        try:
            if self.repo_type == "gitee":
                async with aiohttp.ClientSession() as session:
                    # Gitee API: GET /api/v5/repos/{owner}/{repo}/contents(/{path})?ref={branch}
                    params = {"ref": self.branch}
                    api_url = f"{self.api_base_url}/contents"
                    _LOGGER.debug("Fetching Gitee repository contents from: %s (branch: %s)", api_url, self.branch)
                    async with session.get(
                        api_url,
                        params=params,
                        headers={"Accept": "application/json"},
                    ) as response:
                        if response.status != 200:
                            response_text = await response.text()
                            _LOGGER.error(
                                "Failed to fetch repository contents from %s: %s - %s", 
                                api_url,
                                response.status,
                                response_text[:200] if response_text else "No response body"
                            )
                            _LOGGER.error(
                                "Repository URL: %s, Parsed path: %s, Branch: %s",
                                self.repo_url,
                                self.api_base_url.replace("https://gitee.com/api/v5/repos/", ""),
                                self.branch
                            )
                            return []

                        data = await response.json()
                        
                        # Handle error response from Gitee API
                        if isinstance(data, dict) and "message" in data:
                            _LOGGER.error(
                                "Gitee API error: %s", data.get("message", "Unknown error")
                            )
                            return []

                        # Extract JS files
                        js_files = [
                            item["name"]
                            for item in data
                            if isinstance(item, dict) 
                            and item.get("name", "").endswith(".js")
                            and item.get("type") == "file"
                        ]
                        return js_files

            elif self.repo_type == "github":
                async with aiohttp.ClientSession() as session:
                    # GitHub API: GET /repos/{owner}/{repo}/contents/{path}?ref={branch}
                    params = {"ref": self.branch}
                    api_url = f"{self.api_base_url}/contents"
                    _LOGGER.debug("Fetching GitHub repository contents from: %s (branch: %s)", api_url, self.branch)
                    async with session.get(
                        api_url,
                        params=params,
                        headers={"Accept": "application/vnd.github.v3+json"},
                    ) as response:
                        if response.status != 200:
                            response_text = await response.text()
                            _LOGGER.error(
                                "Failed to fetch repository contents from %s: %s - %s", 
                                api_url,
                                response.status,
                                response_text[:200] if response_text else "No response body"
                            )
                            _LOGGER.error(
                                "Repository URL: %s, Parsed path: %s, Branch: %s",
                                self.repo_url,
                                self.api_base_url.replace("https://api.github.com/repos/", ""),
                                self.branch
                            )
                            return []

                        data = await response.json()
                        
                        # Handle error response from GitHub API
                        if isinstance(data, dict) and "message" in data:
                            _LOGGER.error(
                                "GitHub API error: %s", data.get("message", "Unknown error")
                            )
                            return []

                        # Extract JS files
                        js_files = [
                            item["name"]
                            for item in data
                            if isinstance(item, dict)
                            and item.get("name", "").endswith(".js")
                            and item.get("type") == "file"
                        ]
                        return js_files

        except Exception as err:
            _LOGGER.error("Error getting repository files: %s", err)
            return []

    async def _download_file(self, filename: str, max_retries: int = 3) -> bool:
        """Download a file from repository with retry mechanism."""
        file_url = f"{self.raw_base_url}/{filename}"
        dest_path = self.community_dir / filename
        
        # Timeout configuration (reduced for faster failure on slow networks)
        timeout = aiohttp.ClientTimeout(
            total=30,  # Total timeout: 30 seconds
            connect=5,  # Connection timeout: 5 seconds
            sock_read=15  # Socket read timeout: 15 seconds
        )
        
        for attempt in range(1, max_retries + 1):
            try:
                _LOGGER.debug("Downloading %s (attempt %d/%d)", filename, attempt, max_retries)
                
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(file_url) as response:
                        if response.status != 200:
                            error_text = ""
                            try:
                                error_text = await response.text()
                            except:
                                pass
                            
                            if attempt < max_retries:
                                _LOGGER.warning(
                                    "Failed to download %s: HTTP %s (attempt %d/%d). Retrying...",
                                    filename, response.status, attempt, max_retries
                                )
                                await asyncio.sleep(2 * attempt)  # Exponential backoff
                                continue
                            else:
                                _LOGGER.error(
                                    "Failed to download %s: HTTP %s. Error: %s",
                                    filename, response.status, error_text[:200] if error_text else "Unknown"
                                )
                                return False

                        # Read content with chunked reading for large files
                        content = b""
                        try:
                            async for chunk in response.content.iter_chunked(8192):
                                content += chunk
                        except Exception as chunk_err:
                            if attempt < max_retries:
                                _LOGGER.warning(
                                    "Error reading content for %s (attempt %d/%d): %s. Retrying...",
                                    filename, attempt, max_retries, chunk_err
                                )
                                await asyncio.sleep(2 * attempt)
                                continue
                            else:
                                _LOGGER.error(
                                    "Error reading content for %s: %s",
                                    filename, chunk_err
                                )
                                return False

                        # Verify content is not empty
                        if not content:
                            if attempt < max_retries:
                                _LOGGER.warning(
                                    "Empty content for %s (attempt %d/%d). Retrying...",
                                    filename, attempt, max_retries
                                )
                                await asyncio.sleep(2 * attempt)
                                continue
                            else:
                                _LOGGER.error("Empty content received for %s", filename)
                                return False

                        # Write file
                        async with aiofiles.open(dest_path, "wb") as f:
                            await f.write(content)

                        _LOGGER.info("Successfully downloaded: %s (%d bytes)", filename, len(content))
                        return True

            except aiohttp.ClientConnectorError as err:
                if attempt < max_retries:
                    _LOGGER.warning(
                        "Connection error downloading %s (attempt %d/%d): %s. Retrying...",
                        filename, attempt, max_retries, str(err)
                    )
                    await asyncio.sleep(2 * attempt)
                    continue
                else:
                    _LOGGER.error(
                        "Connection error downloading %s after %d attempts: %s",
                        filename, max_retries, str(err)
                    )
                    return False
                    
            except aiohttp.ServerTimeoutError as err:
                if attempt < max_retries:
                    _LOGGER.warning(
                        "Timeout error downloading %s (attempt %d/%d): %s. Retrying...",
                        filename, attempt, max_retries, str(err)
                    )
                    await asyncio.sleep(2 * attempt)
                    continue
                else:
                    _LOGGER.error(
                        "Timeout error downloading %s after %d attempts: %s",
                        filename, max_retries, str(err)
                    )
                    return False
                    
            except asyncio.TimeoutError as err:
                if attempt < max_retries:
                    _LOGGER.warning(
                        "Timeout downloading %s (attempt %d/%d): %s. Retrying...",
                        filename, attempt, max_retries, str(err)
                    )
                    await asyncio.sleep(2 * attempt)
                    continue
                else:
                    _LOGGER.error(
                        "Timeout downloading %s after %d attempts: %s",
                        filename, max_retries, str(err)
                    )
                    return False
                    
            except Exception as err:
                if attempt < max_retries:
                    _LOGGER.warning(
                        "Error downloading %s (attempt %d/%d): %s. Retrying...",
                        filename, attempt, max_retries, str(err)
                    )
                    await asyncio.sleep(2 * attempt)
                    continue
                else:
                    _LOGGER.error(
                        "Error downloading %s after %d attempts: %s",
                        filename, max_retries, str(err)
                    )
                    return False
        
        return False

    async def _get_existing_resources(self) -> set[str]:
        """Get existing resource URLs from resources file."""
        if not await self._file_exists(self.resources_file):
            return set()

        try:
            async with aiofiles.open(self.resources_file, "r", encoding="utf-8") as f:
                content = await f.read()
                data = json.loads(content)
                items = data.get("data", {}).get("items", [])
                return {item.get("url", "") for item in items if item.get("url")}
        except Exception as err:
            _LOGGER.error("Error reading resources file: %s", err)
            return set()

    async def _get_existing_resources_data(self) -> list[dict[str, Any]]:
        """Get existing resource items from resources file."""
        if not await self._file_exists(self.resources_file):
            return []

        try:
            async with aiofiles.open(self.resources_file, "r", encoding="utf-8") as f:
                content = await f.read()
                data = json.loads(content)
                items = data.get("data", {}).get("items", [])
                return items if isinstance(items, list) else []
        except Exception as err:
            _LOGGER.error("Error reading resources file: %s", err)
            return []

    async def _add_resource(self, resource_url: str) -> bool:
        """Add a resource to the resources file."""
        try:
            # Read existing resources
            if await self._file_exists(self.resources_file):
                async with aiofiles.open(self.resources_file, "r", encoding="utf-8") as f:
                    content = await f.read()
                    data = json.loads(content)
            else:
                data = {
                    "version": 1,
                    "minor_version": 1,
                    "key": "lovelace_resources",
                    "data": {"items": []},
                }

            # Ensure data structure is correct
            if "data" not in data:
                data["data"] = {"items": []}
            if "items" not in data["data"]:
                data["data"]["items"] = []

            # Check if resource already exists
            existing_urls = {item.get("url", "") for item in data["data"]["items"]}
            if resource_url in existing_urls:
                _LOGGER.debug("Resource already exists: %s", resource_url)
                return True

            # Generate unique ID
            resource_id = str(uuid.uuid4()).replace("-", "")

            # Add new resource
            new_item = {"id": resource_id, "url": resource_url, "type": "module"}
            data["data"]["items"].append(new_item)

            # Ensure all required fields are present
            if "version" not in data:
                data["version"] = 1
            if "minor_version" not in data:
                data["minor_version"] = 1
            if "key" not in data:
                data["key"] = "lovelace_resources"

            # Write back to file
            json_content = json.dumps(data, indent=2, ensure_ascii=False)
            async with aiofiles.open(self.resources_file, "w", encoding="utf-8") as f:
                await f.write(json_content)

            _LOGGER.info("Successfully added resource to Lovelace: %s (ID: %s)", resource_url, resource_id)
            _LOGGER.debug("Resource file now contains %d items", len(data["data"]["items"]))
            return True

        except Exception as err:
            _LOGGER.error("Error adding resource %s: %s", resource_url, err, exc_info=True)
            return False

    async def _remove_resource(self, resource_url: str) -> bool:
        """Remove a resource from the resources file."""
        try:
            if not await self._file_exists(self.resources_file):
                return False

            # Read existing resources
            async with aiofiles.open(self.resources_file, "r", encoding="utf-8") as f:
                content = await f.read()
                data = json.loads(content)

            # Remove resource
            items = data.get("data", {}).get("items", [])
            data["data"]["items"] = [
                item for item in items if item.get("url") != resource_url
            ]

            # Write back to file
            async with aiofiles.open(self.resources_file, "w", encoding="utf-8") as f:
                await f.write(json.dumps(data, indent=2, ensure_ascii=False))

            return True

        except Exception as err:
            _LOGGER.error("Error removing resource: %s", err)
            return False

    async def _migrate_resource(self, old_url: str, new_url: str) -> bool:
        """Migrate a resource from old URL to new URL."""
        try:
            if not await self._file_exists(self.resources_file):
                return False

            # Read existing resources
            async with aiofiles.open(self.resources_file, "r", encoding="utf-8") as f:
                content = await f.read()
                data = json.loads(content)

            # Find and update resource
            items = data.get("data", {}).get("items", [])
            updated = False
            for item in items:
                if item.get("url") == old_url:
                    item["url"] = new_url
                    updated = True
                    _LOGGER.debug("Updated resource URL from %s to %s", old_url, new_url)
                    break

            if not updated:
                _LOGGER.warning("Resource with URL %s not found for migration", old_url)
                return False

            # Write back to file
            async with aiofiles.open(self.resources_file, "w", encoding="utf-8") as f:
                await f.write(json.dumps(data, indent=2, ensure_ascii=False))

            _LOGGER.info("Successfully migrated resource from %s to %s", old_url, new_url)
            return True

        except Exception as err:
            _LOGGER.error("Error migrating resource from %s to %s: %s", old_url, new_url, err)
            return False

    async def _init_resources_file(self) -> None:
        """Initialize resources file."""
        data = {
            "version": 1,
            "minor_version": 1,
            "key": "lovelace_resources",
            "data": {"items": []},
        }

        async with aiofiles.open(self.resources_file, "w", encoding="utf-8") as f:
            await f.write(json.dumps(data, indent=2, ensure_ascii=False))

    async def _file_exists(self, path: Path) -> bool:
        """Check if file exists."""
        return path.exists()

    def start_auto_update(self) -> None:
        """Start auto-update task."""
        if self._auto_update_task is None or self._auto_update_task.done():
            self._auto_update_task = asyncio.create_task(self._auto_update_loop())

    def stop_auto_update(self) -> None:
        """Stop auto-update task."""
        if self._auto_update_task and not self._auto_update_task.done():
            self._auto_update_task.cancel()

    async def _auto_update_loop(self) -> None:
        """Auto-update loop."""
        while True:
            try:
                await asyncio.sleep(self.update_interval)
                _LOGGER.info("Auto-updating cards...")
                await self.async_update_cards()
            except asyncio.CancelledError:
                _LOGGER.info("Auto-update cancelled")
                break
            except Exception as err:
                _LOGGER.error("Error in auto-update: %s", err)

