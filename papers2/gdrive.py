from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
from pydrive2.fs import GDriveFileSystem
from googleapiclient.errors import HttpError
from pathlib import Path
import logging as log
import os

# testing code

# gauth = GoogleAuth()
# gauth.LocalWebserverAuth()
#
# drive = GoogleDrive(gauth)
#
#
# #this is pretty neat, for convenience, but it does not do a proper 'backend move'. Maybe I can cobble it together if I can extract
# # some lower-level access from pydrive to the google API
# # e.g. drive.auth.service should do it!
#
# fs = GDriveFileSystem(
#     "root",
#     client_id=drive.auth.attr['client_config']['client_id'],
#     client_secret=drive.auth.attr['client_config']['client_secret'],
#     client_json_file_path="/Users/Shared/dev/papers2/keyfile.json",
# )
#
# #note, google drive has its root at 'root'
# fs.exists('root/Papers2/Articles')
# fs.exists("root/Zotero/Journal Article")
#
# #works great, just like that, but a) very slow and b) seems to involve a upload, though I--can't tell
# fs.cp('root/Papers2/Articles/A/Abe/Abe 2008 - Neural Correlates of True Memory False Memory and Deception - Cereb Cortex.pdf',
#       'root/Zotero/Journal Article/A/Abe/')
#
# # it has a nice way to walk the hierarchy to get item ids. Can I then do a simple move and update?
# fs._get_item_id('root/Papers2/Articles/A/Abe/Abe 2008 - Neural Correlates of True Memory False Memory and Deception - Cereb Cortex.pdf')
# fs._get_item_id('root/Zotero/Journal Article/A/AAA/',create=True) #recursive mkdir!
#
#
# drive_service = drive.auth.service
# file_id = fs._get_item_id('root/Papers2/Articles/A/Abe/Abe 2008 - Neural Correlates of True Memory False Memory and Deception - Cereb Cortex copy.pdf')
# new_folder_id = fs._get_item_id('root/Zotero/Journal Article/A/AAA/',create=True)

from abc import ABCMeta, abstractmethod

GROOT = "root"

#simple abstract class to define something that can move an attachment found at a path to a new directory
# __init__ does any impementation-specific initialization
# move(from_path, to_path) does the actual moving. paths are _relative_ to the drive folder

class AttachmentMover(object, metaclass=ABCMeta):
    @abstractmethod
    def __init__(self,**kwargs):
        pass

    @abstractmethod
    def move(self, from_path, to_path):
        pass



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
        gauth.LocalWebserverAuth()

        #sometimes fails; try removing credentials file
        if gauth.service is None:
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
            client_id=self.drive.auth.attr['client_config']['client_id'],
            client_secret=self.drive.auth.attr['client_config']['client_secret'],
            client_json_file_path=json_file
        )

    #paths are absolute paths within the google drive, e.g. for My Drive/Dir -> /Dir
    def move(self, from_path, to_path):
        drive_service = self.drive.auth.service
        if drive_service is None:
            return None

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
            log.error(f'An error occurred: {error}')
            file = None

        return file


