from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
from pydrive2.fs import GDriveFileSystem
from googleapiclient.errors import HttpError
from pathlib import Path
import logging as log
import os
import shutil

from abc import ABCMeta, abstractmethod

#simple abstract class to define something that can move an attachment found at a path to a new directory
# __init__ does any impementation-specific initialization
# move(from_path, to_path) does the actual moving. paths are _relative_ to the drive folder

class AttachmentMover(object, metaclass=ABCMeta):
    @abstractmethod
    def __init__(self,**kwargs):
        pass

    @abstractmethod
    def move(self, from_path, to_path, keep_copy=False):
        return False

#attachment mover for files stored locally. (Untested)
class localAttachmentMover(AttachmentMover):

    def __init__(self, **kwargs):
        pass

    def move(self, from_path, to_path, keep_copy=True):
        try:
            if not os.path.isdir(os.path.dirname(to_path)):
                Path(os.path.dirname(to_path)).mkdir(parents=True, exist_ok=True)
            if keep_copy:
                shutil.copy2(from_path, to_path)
            else:
                shutil.move(from_path, to_path)
        except Exception as e:
            log.error(f'An error occurred moving {from_path} to {to_path}:\n {e}')
            return False

        return True


# Class to encapsulate the handling of moving files within google drive
# intended purpose is to move attachments from  Papers2/ to Zotero/ attachment directories
#
# using three apis together: pydrive2 to make authentication and accessing secrets easy as well as open a service
# GDriveFileSystem for its ease in finding item ids from paths
# raw google API to update parent folders on the backend, avoiding any downloading and uploading of files,
#   especially for on-demand streamed filesystems

class GDriveAttachmentMover(AttachmentMover):
    def __init__(self, settings_file="settings.yaml"):

        settings_path = Path(settings_file).parent.absolute()
        cred_file = str(settings_path.joinpath("credentials.json"))
        json_file = str(settings_path.joinpath("keyfile.json"))

        gauth = GoogleAuth(settings_file=str(settings_file))
        gauth.LoadCredentials()
        if gauth.credentials is None:
            # Authenticate if they're not there
            gauth.LocalWebserverAuth()
        elif gauth.access_token_expired:
            # Refresh them if expired
            gauth.Refresh()
        else:
            # Initialize the saved creds
            gauth.Authorize()

        # Save the current credentials to a file
        gauth.SaveCredentials()

        #sometimes fails; try removing credentials file--bruteforce, but failsafe
        if gauth.service is None:
            # breakpoint()
            if os.path.exists(cred_file):
                os.remove(cred_file)
            if os.path.exists(json_file):
                os.remove(json_file)
            gauth = GoogleAuth(settings_file=str(settings_file))
            gauth.LocalWebserverAuth()
            if gauth.service is None:
                raise Exception("Cannot authenticate google drive!")

        self.drive = GoogleDrive(gauth)
        self.fs = GDriveFileSystem(
            "root",
            client_id=self.drive.auth.attr['settings']['client_config']['client_id'],
            client_secret=self.drive.auth.attr['settings']['client_config']['client_secret'],
            client_json_file_path=json_file
        )

    #paths are absolute paths within the google drive, e.g. for My Drive/Dir -> /Dir
    # returns True/False if succeeded/failed
    def move(self, from_path, to_path, keep_copy=False):
        GROOT = "root"
        drive_service = self.drive.auth.service
        if drive_service is None:
            return False

        file_id = self.fs._get_item_id(GROOT + from_path)
        to_dir = os.path.dirname(to_path)
        to_filename = os.path.basename(to_path)
        new_folder_id = self.fs._get_item_id(GROOT + to_dir, create=True)

        try:
            file = drive_service.files().get(fileId=file_id, fields='parents').execute()
            previous_parents = ",".join(d['id'] for d in file['parents'])
            file = drive_service.files().update(fileId=file_id, addParents=new_folder_id,
                                                removeParents=previous_parents,
                                                fields='id, parents').execute()
            file = drive_service.files().patch(fileId=file_id, body={'title': to_filename},
                                               fields='title').execute()
            log.debug(f'File with ID "{file_id}" has been moved to the new folder with ID "{new_folder_id}".')
        except HttpError as error:
            log.error(f'An http error occurred moving {from_path} to {to_path}:\n {error}')
            return False
        except Exception as e:
            log.error(f'An error occurred moving {from_path} to {to_path}:\n {e}')

        return True


