# Wrapper around a pyzotero session that can convert Papers2
# entities to zotero items.
#
# TODO: handle archived papers?
# TODO: user-definable date format; for now using YYYY-MM-DD
# TODO: use relations to link book chapters to parent volume

from datetime import datetime
import logging as log
import sys
import os

from pyzotero.zotero import Zotero
from .schema import PubType, IDSource, KeywordType, Label
from .util import Batch, JSONWriter

# mapping of papers2 publication types 
# to Zotero item types 
ITEM_TYPES = {

    PubType.BOOK                : 'book',
    PubType.BOOK_SECTION        : 'bookSection',
    PubType.THESIS              : 'thesis',
    PubType.E_BOOK              : 'book',
    PubType.PAMPHLET            : 'document',
    PubType.WEBSITE             : 'webpage',
    PubType.POSTER              : 'presentation',
    PubType.PRESENTATION        : 'presentation',
    PubType.ABSTRACT            : 'presentation',
    PubType.LECTURE             : 'presentation',
    PubType.PHOTO               : 'artwork',
    PubType.SOFTWARE            : 'computerProgram',
    PubType.DATA_FILE           : 'dataset',
    PubType.JOURNAL_ARTICLE     : 'journalArticle',
    PubType.MAGAZINE_ARTICLE    : 'magazineArticle',
    PubType.NEWSPAPER_ARTICLE   : 'newspaperArticle',
    PubType.WEBSITE_ARTICLE     : 'webpage',
    PubType.MANUSCRIPT          : 'manuscript',
    PubType.PREPRINT            : 'preprint',
    PubType.CONFERENCE_PAPER    : 'conferencePaper',
    PubType.PATENT              : 'patent',
    PubType.REPORT              : 'report',
    PubType.TECHREPORT          : 'report',
    PubType.SCIENTIFIC_REPORT   : 'report',
    PubType.GRANT               : 'report',
    PubType.ASSIGNMENT          : 'report',
    PubType.REFERENCE           : 'report',
    PubType.PROTOCOL            : 'report'
}

# mapping of papers2 publication types to zotero Folder types
#   to use when moving an attachment over from Papers2 directory to Zotero
#   linked-files directory (as managed by ZOTFILE, configured to use %T type as top level folders)
FOLDER_MAP = {
    PubType.BOOK: 'Book',
    PubType.BOOK_SECTION: 'Book Section',
    PubType.THESIS: 'Thesis',
    PubType.E_BOOK: 'Book',
    PubType.PAMPHLET: 'Document',
    PubType.WEBSITE: 'Web Page',
    PubType.POSTER: 'Presentation',
    PubType.PRESENTATION: 'Presentation',
    PubType.ABSTRACT: 'Presentation',
    PubType.LECTURE: 'Presentation',
    PubType.PHOTO: 'Artwork',
    PubType.SOFTWARE: 'Software',
    PubType.DATA_FILE: 'Dataset',
    PubType.JOURNAL_ARTICLE: 'Journal Article',
    PubType.MAGAZINE_ARTICLE: 'Magazine Article',
    PubType.NEWSPAPER_ARTICLE: 'Newspaper Article',
    PubType.WEBSITE_ARTICLE: 'Web Page',
    PubType.MANUSCRIPT: 'Journal Article',
    PubType.PREPRINT: 'Preprint',
    PubType.CONFERENCE_PAPER: 'Conference Paper',
    PubType.PATENT: 'Patent',
    PubType.REPORT: 'Report',
    PubType.TECHREPORT: 'Report',
    PubType.SCIENTIFIC_REPORT: 'Report',
    PubType.GRANT: 'Report',
    PubType.ASSIGNMENT: 'Report',
    PubType.REFERENCE: 'Report',
    PubType.PROTOCOL: 'Report'
}

# folder relative to google drive root for the two sets of attachment directories
PBASE = '/Papers2'
ZBASE = '/Zotero'

class Extract(object):
    def __init__(self, fn=None, num_values=1):
        self.fn = fn
        self.num_values = num_values
    
    def extract(self, pub, context, default=None):
        if self.fn is not None:
            value = self.fn(pub)
        
        else:
            try:
                value = self.get_value(pub, context)
            
            except NotImplementedError:
                value = default
        
        if value is not None:
            if isinstance(value, str) or isinstance(value, str):
                value = self.format(value)

            else:
                try:
                    value = tuple(value)
                    nvals = len(value)
                    return_tuple = self.num_values != 1
                    if self.num_values is not None:
                        nvals = min(nvals, self.num_values)
                    value = self.format_tuple(value, nvals)
                    if value is not None:
                        if len(value) == 0:
                            value = None
                        elif nvals == 1 and not return_tuple:
                            value = value[0]
                
                except TypeError:
                    value = self.format(value)
        
        return value
    
    def format_tuple(self, values, nvals):
        values = [_f for _f in values if _f]
        nvals = min(nvals, len(values))
        if nvals > 0:
            if len(values) < nvals:
                values = values[0:nvals]
            return list(map(self.format, values))
    
    def format(self, value):
        return value
    
    def get_value(self, pub, context):
        raise NotImplementedError()

class ExtractRange(Extract):
    def format_tuple(self, values, nvals):
        return ("{0}-{1}".format(*values),)

class ExtractTimestamp(Extract):
    def format(self, value):
        return datetime.utcfromtimestamp(value).strftime('%Y-%m-%dT%H:%M:%SZ')

class ExtractBundle(Extract):
    def get_value(self, pub, context):
        journal = context.papers2.get_bundle(pub)
        if journal is not None:
            return journal.title
        else:
            return pub.bundle_string

class ExtractPubdate(Extract):
    def format(self, pub_date):
        date_str = ''
        
        year = pub_date[2:6]
        if year is not None:
            date_str = year
            
            month = pub_date[6:8]
            if month is not None:
                if month == "00":
                    month = "01"
                date_str += "-" + month
                
                day = pub_date[8:10]
                if day is not None:
                    if day == "00":
                        day = "01"
                    date_str += "-" + day
        
        # TODO: check date for validity
        
        return date_str

class ExtractCreators(Extract):
    def __init__(self):
        Extract.__init__(self, num_values=None)
    
    def get_value(self, pub, context):
        return context.papers2.get_pub_authors(pub)
    
    def format(self, author):
        if author.type == 0:
            creator_type = 'author'
        elif author.type == 1:
            creator_type = 'editor'
        else:
            raise Exception(f"Unsupported author type {author.type}")
        
        if author.institutional > 0:
            return { 
                'creatorType': creator_type,
                'name': author.surname
            }
        else:
            return { 
                'creatorType': creator_type,
                'firstName': author.prename,
                'lastName': author.surname
            }

class ExtractIdentifier(Extract):
    def __init__(self, id_sources, num_values=1):
        Extract.__init__(self, num_values=num_values)
        self.id_sources = id_sources
        
    def get_value(self, pub, context):
        idents = []
        for src in self.id_sources:
            idents.extend(context.papers2.get_identifiers(pub, src))
        return idents
    
    def format(self, value):
        return value.remote_id

class ExtractPubmedID(ExtractIdentifier):
    def __init__(self):
        ExtractIdentifier.__init__(self, (IDSource.PUBMED, IDSource.PMC))
    
    def format(self, value):
        return f"PMID: {value.remote_id}"

class ExtractUrl(Extract):
    def get_value(self, pub, context):
        return context.papers2.get_urls(pub)
        
    def format(self, value):
        return value.remote_id

class ExtractKeywords(Extract):
    def __init__(self):
        Extract.__init__(self, num_values=None)
        
    def get_value(self, pub, context):
        keywords = []
        if 'user' in context.keyword_types:
            keywords.extend({"tag": k.name} for k in context.papers2.get_keywords(pub, KeywordType.USER))
        if 'auto' in context.keyword_types:
            keywords.extend({"tag": k.name, "type": 1} for k in context.papers2.get_keywords(pub, KeywordType.AUTO)) # 1 is auto *https://github.com/bwiernik/zotero-shortdoi/issues/16)
        if 'label' in context.keyword_types:
            label = context.label_map.get(context.papers2.get_label_name(pub), None)
            if label is not None:
                keywords.append({"tag": label})
        return keywords

class ExtractCollections(Extract):
    def __init__(self):
        Extract.__init__(self, num_values=None)
    
    def get_value(self, pub, context):
        if len(context.collections) > 0:
            collections = []
            for c in context.papers2.get_collections(pub):
                if c.name in context.collections:
                    collections.append(context.collections[c.name])
            return collections
                
class AttrExtract(Extract):
    def __init__(self, key):
        self.key = key
    
    def get_value(self, pub, context):
        return getattr(pub, self.key)

EXTRACTORS = dict(
    DOI=                    Extract(lambda pub: pub.doi),
    ISBN=                   ExtractIdentifier((IDSource.ISBN, IDSource.ISSN)),
    abstractNote=           Extract(lambda pub: pub.summary),
    accessDate=             ExtractTimestamp(lambda pub: pub.imported_date),
    collections=            ExtractCollections(),
    creators=               ExtractCreators(),
    date=                   ExtractPubdate(lambda pub: pub.publication_date),
    edition=                Extract(lambda pub: pub.version),
    extra=                  ExtractPubmedID(),
    issue=                  Extract(lambda pub: pub.number),
    journalAbbreviation=    Extract(lambda pub: pub.bundle_string),
    language=               Extract(lambda pub: pub.language),
    number=                 Extract(lambda pub: pub.document_number),
    pages=                  ExtractRange(lambda pub: (pub.startpage, pub.endpage)),
    numPages=               Extract(lambda pub: pub.startpage),
    place=                  Extract(lambda pub: pub.place),
    publicationTitle=       ExtractBundle(),
    publisher=              Extract(lambda pub: pub.publisher),
    rights=                 Extract(lambda pub: pub.copyright),
    tags=                   ExtractKeywords(),
    title=                  Extract(lambda pub: pub.title),
    university=             ExtractBundle(),
    url=                    ExtractUrl(),
    volume=                 Extract(lambda pub: pub.volume)
)

class ZoteroImporter(object):
    def __init__(self, library_id, library_type, api_key, papers2, attachmentMover, zotero_linked_attachment_base=None,
            keyword_types=('user','auto','label'), label_map={}, add_to_collections=[],
            upload_attachments="all", batch_size=50, checkpoint=None, dryrun=None, retry_failed=False):
        self.client = Zotero(library_id, library_type, api_key)
        self.papers2 = papers2
        self.attachmentMover = attachmentMover
        self.labd = zotero_linked_attachment_base
        self.keyword_types = keyword_types
        self.label_map = label_map
        self.upload_attachments = upload_attachments
        self.checkpoint = checkpoint
        self.dryrun = JSONWriter(dryrun) if dryrun is not None else None
        self.retry_failed = retry_failed
        self._batch = Batch(batch_size)
        self._load_collections(add_to_collections)
    
    # Load Zotero collections and create any
    # Papers2 collections that don't exist.
    # TODO: need to handle collection hierarchies
    def _load_collections(self, add_to_collections):
        self.collections = {}
        if add_to_collections is None:
            add_to_collections = list(c.name for c in self.papers2.get_collections())

        if len(add_to_collections) > 0:
            if self.dryrun is not None:
                for c in add_to_collections:
                    self.collections[c] = f"<{c}>"  #for debugging during dry-runs
                
            else:
                # fetch existing zotero collections
                existing_collections = {}
                for zc in self.client.collections():
                    data = zc['data']
                    existing_collections[data['name']] = data['key']
                
                # add any papers2 collections that do not already exist
                payload = []
                for pc in add_to_collections:
                    if pc not in existing_collections:
                        payload.append(dict(name=pc))
                if len(payload) > 0:
                    self.client.create_collection(payload)
            
                # re-fetch zotero collections in order to get keys
                for zc in self.client.collections():
                    data = zc['data']
                    if data['name'] in add_to_collections:
                        self.collections[data['name']] = data['key']
    
    # add papers pub to zotero batch
    def add_pub(self, pub):
        # ignore publications we've already imported
        if self.checkpoint is not None and self.checkpoint.contains(pub.ROWID):
            log.info(f"Skipping already imported publication {pub.ROWID}: {pub.title}")
            return False

        if self.checkpoint is not None and self.checkpoint.contains_failed(pub.ROWID):
            if self.retry_failed:
                log.warning(f"Retrying a failed publication {pub.ROWID}: {pub.title}")
            else:
                log.info(f"Skipping already failed publication {pub.ROWID}: {pub.title}")
                return False
        
        # convert the Papers2 publication type to a Zotero item type
        item_type = ITEM_TYPES[self.papers2.get_pub_type(pub)]

        # get the template to fill in for an item of this type
        item = self.client.item_template(item_type)

        # fill in template fields
        for key, value in item.items():
            if key in EXTRACTORS:
                value = EXTRACTORS[key].extract(pub, self, value)
                if value is not None:
                    item[key] = value

        # append tags based on Collection membership
        collections = self.papers2.get_collections(pub).all()
        tags = list(f'C:{c.name}' for c in collections) #fails properly if no collections, returning empty list

        # add tag if we ever cited it
        if pub.citekey is not None:
            tags.append('&cited')

        # add a tag with rating
        if pub.rating > 0:
            tags.append('⭐' * pub.rating) # Essential to use this symbol as tags plugin displays by filename

        # add tags directly to item. Zotero tags needs to be a dict, not a list (see pyzotero.add_tags)
        item['tags'].extend({"tag": tag} for tag in tags)

        # add notes, if any
        notes = []
        if pub.notes is not None and len(pub.notes) > 0:
            notes.append(pub.notes)
        
        reviews = self.papers2.get_reviews(pub)
        for r in reviews:
            notes.append(f"{r.content} Rating: {r.rating}")


        # get paths to attachments
        attachments = []
        if self.upload_attachments == "all" or (
                self.upload_attachments == "unread" and pub.times_read == 0):
            attachments = list(self.papers2.get_attachments(pub)) #each is a tuple (filename, mime, papersItem)
        

        # add to batch and checkpoint
        self._batch.add(item, notes, attachments)
        if self.checkpoint is not None:
            self.checkpoint.add(pub.ROWID)
        
        # commit the batch if it's full
        self._commit_batch()
        
        return True
    
    def close(self):
        if self._batch is not None:
            self._commit_batch(force=True)
            self._batch = None
        if self.dryrun is not None:
            self.dryrun.close()
            
    def _commit_batch(self, force=False):
        if self._batch.is_full or (force and not self._batch.is_empty):
            try:
                if self.dryrun is not None:
                    for item, notes, attachments in self._batch.iter():
                        self.dryrun.write(item, notes, attachments)

                else:
                    # upload metadata
                    item_status = self.client.create_items(self._batch.items)
                    successes = {}
                    successes.update(item_status['success'])
                    successes.update(item_status['unchanged'])

                    if len(item_status['failed']) > 0:
                        for status_idx, status_msg in item_status['failed'].items():
                            item_idx = int(status_idx)
                            rowid = self.checkpoint.get(item_idx)
                            # remove failures from the checkpoint
                            if self.checkpoint is not None:
                                self.checkpoint.add_failed(rowid)
                            item = self._batch.items[item_idx]
                            log.error(f"Item creation failed for papers ID {rowid}\n Zotero item {item['title']}; code {status_msg['code']}; {status_msg['message']}")
                    
                    for k, objKey in successes.items():
                        item_idx = int(k)
                        rowid = self.checkpoint.get(item_idx)

                        log.warning(f"ROWID: {rowid}. Add Notes and Attachments...")

                        # add notes
                        notes = self._batch.notes[item_idx]
                        if len(notes) > 0:
                            note_batch = []
                            for note_text in notes:
                                note = self.client.item_template('note')
                                note['parentItem'] = objKey
                                note['note'] = note_text
                                note_batch.append(note)
                            
                            note_status = self.client.create_items(note_batch)
                            
                            if len(note_status['failed']) > 0:
                                for status_idx, status_msg in note_status['failed'].items():
                                    note_idx = int(status_idx)
                                    # just warn about these failures
                                    note = note_batch[note_idx]
                                    log.error(f"ROWID: {rowid}. Failed to create note {note['note']} for item item {self._batch.items[status_idx]['title']}; code {status_msg['code']}; {status_msg['message']}")
                                    self.checkpoint.add_failed(rowid)

                        # upload attachments and add items to collections
                        # changed this to link instead
                        if self.upload_attachments != "none":
                        
                            # TODO: modify pyzotero to pass MIME type for contentType key
                            attachments = list(path for path, mime, type in self._batch.attachments[item_idx])

                            if len(attachments) == 0:
                                log.warning("No Attachments.")
                            else:
                                # if no linked attachment base dir is specified, then upload attachments
                                if self.labd is None or self.attachmentMover is None:
                                    try:
                                        self.client.attachment_simple(attachments, objKey)
                                    # This is to work around a bug in pyzotero where an exception is
                                    # thrown if an attachment already exists
                                    except KeyError:
                                        log.warning(f"One or more attachment already exists: {','.join(attachments)}")

                                # if LABD is specified, then create a linked attachment and move from Papers2 to Zotero attachment dires
                                else:
                                    a = self.client.item_template('attachment', 'linked_file')  # single template item
                                    for p2path, mime, ptype in self._batch.attachments[item_idx]:

                                        # dissect path of original, reconstitute for zotero
                                        p2relpath = os.path.relpath(p2path, self.papers2.folder)
                                        rp = p2relpath.split('/') #used to compose zotero output path
                                        # p2folder = rp[0]
                                        # p2initial = rp[1]
                                        # p2author = rp[2]
                                        # filename = rp[-1]
                                        #clean up initial for output path
                                        rp[1] = rp[1][0]
                                        is_supplement = ((len(rp) == 5) & (rp[3] == 'Supplemental'))
                                        if is_supplement:
                                            del rp[3]
                                            rp[-1] = 'Supplement-' + rp[-1]

                                        from_path = os.path.join(PBASE, p2relpath)

                                        filename = rp[-1]
                                        zfolder = FOLDER_MAP[ptype]
                                        zrelpath = os.path.join(zfolder, *rp[1:])
                                        to_path = os.path.join(ZBASE, zrelpath)

                                        # fill in attachment item
                                        #a['parent'] = objKey
                                        a['path'] = 'attachments:' + zrelpath #prefix needed for linked attachments, apparently!
                                        a['contentType'] = mime
                                        a['title'] = filename
                                        a['tags'] = [];
                                        if is_supplement:
                                            a['tags'] = [{'tag': '&SUPP'}]
                                        # File creation time: Unix uses st_birthtime, not ctime
                                        # https://docs.python.org/3/library/os.html#os.stat_result
                                        # Since Papers2 is mac-only, no problem here
                                        a['accessDate'] = ""
                                        if os.path.exists(p2path):
                                            filestat = os.stat(p2path)
                                            a['accessDate'] = datetime.utcfromtimestamp(filestat.st_birthtime).strftime('%Y-%m-%dT%H:%M:%SZ')

                                        try:
                                            log.debug("Creating zotero link attachment item...")
                                            link_status = self.client.create_items([a], parentid=objKey)
                                            if len(link_status['success']) == 1:
                                                # attachment has been successfully created
                                                log.debug(f"Success. Now Moving \n{from_path} to \n{to_path}.")
                                                if os.path.exists(p2path):
                                                    if self.attachmentMover.move(from_path, to_path):
                                                        log.info(f"Moved {filename} P2Z!")
                                                    else:
                                                        log.error(f"Attachment move of {filename} failed")
                                                        self.checkpoint.add_failed(rowid)
                                                else:
                                                    log.error(f"Original file {p2path} seems not to exist. No move done.")
                                                    self.checkpoint.add_failed(rowid)
                                            else:
                                                log.error(f"Attachment item not created for papers ROWID {rowid},  {p2relpath}")
                                                self.checkpoint.add_failed(rowid)

                                        except Exception as e:
                                            log.error(f"attachment link for {p2relpath} could not be made")
                                            log.error(f"Error: {e}")
                                            self.checkpoint.add_failed(rowid)

                    # update checkpoint
                    if self.checkpoint is not None:
                        self.checkpoint.commit()
                
                    log.warning(
                        f"Batch committed: {len(item_status['success'])} items created and {len(item_status['unchanged'])} items unchanged out of {self._batch.size} attempted"
                        )
                    log.warning(f"Total added: {len(self.checkpoint.ids)}\n  Failed ids: {self.checkpoint.failed}")
            
            except Exception as e:
                # should handle specific errors above, but if anything else, repoort
                log.error(f"Unhandled error importing items to Zotero:\n{e}")
                log.error(f"Checkpoint:\nCommitted: {self.checkpoint.ids}\nUncommitted: {self.checkpoint._uncommitted}\nFailed: {self.checkpoint.failed}")
                if self.checkpoint is not None:
                    self.checkpoint.rollback()
                raise
            
            finally:
                self._batch.clear()
