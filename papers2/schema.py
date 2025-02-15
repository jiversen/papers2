# Wrapper around Papers2 database, using SQLAlchemy for ORM. 
# Note that all these functions return unexecuted queries,
# so they can either be iterated over, executed with a call
# to a Query method, or implicitly executed by converting to
# a list (list(query)).

from collections import namedtuple
import os

from sqlalchemy import create_engine
from sqlalchemy.ext.automap import automap_base
from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import or_

from .util import enum

# assign type by papers subtype id. Not an exhaustive list, but all I have in library. Other types will be silently ignored.
#   if updating, be sure to also update mappings in zotero.py
PubAttrs = namedtuple("PubAttrs", ("name", "id"))
PubType = enum('PubType',
    BOOK=               PubAttrs("Book",                0),
    BOOK_SECTION=       PubAttrs("BookSection",         -1000),
    THESIS=             PubAttrs("Thesis",              10),
    E_BOOK=             PubAttrs("eBook",               20),
    PAMPHLET=           PubAttrs("Pamphlet",            30),
    WEBSITE=            PubAttrs("Website",             300),
    POSTER=             PubAttrs("Poster",              313),
    PRESENTATION=       PubAttrs("Website",             314),
    ABSTRACT=           PubAttrs("Website",             315),
    LECTURE=            PubAttrs("Website",             319),
    PHOTO=              PubAttrs("Website",             325),
    SOFTWARE=           PubAttrs("Software",            341),
    DATA_FILE=          PubAttrs("Data File",           345),
    JOURNAL_ARTICLE=    PubAttrs("Journal Article",     400),
    MAGAZINE_ARTICLE=   PubAttrs("Magazine Article",    401),
    NEWSPAPER_ARTICLE=  PubAttrs("Newspaper Article",   402),
    WEBSITE_ARTICLE=    PubAttrs("Website Article",     403),
    MANUSCRIPT=         PubAttrs("Manuscript",          410),
    PREPRINT=           PubAttrs("Preprint",            415),
    CONFERENCE_PAPER=   PubAttrs("Conference Paper",    420),
    PATENT=             PubAttrs("Patent",              500),
    REPORT=             PubAttrs("Report",              700),
    TECHREPORT=         PubAttrs("Technical Report",    701),
    SCIENTIFIC_REPORT=  PubAttrs("Scientific Report",   702),
    GRANT=              PubAttrs("Grant",               703),
    ASSIGNMENT=         PubAttrs("Assignment",          704),
    REFERENCE=          PubAttrs("Reference",           713),
    PROTOCOL=           PubAttrs("Protocol",            717)
)
pub_type_id_to_pub_type = dict((t.id,t) for t in PubType.__values__)

IDSource = enum("IDSource",
    PUBMED= "gov.nih.nlm.ncbi.pubmed",
    PMC=    "gov.nih.nlm.ncbi.pmc",
    ISBN=   "org.iso.isbn",
    ISSN=   "org.iso.issn",
    USER=   "com.mekentosj.papers2.user"
)

KeywordType = enum("KeywordType",
    AUTO = 0,
    USER = 99
)

LabelAttrs = namedtuple("LabelAttrs", ("name", "num"))
Label = enum("Label",
    NONE=       LabelAttrs("None",      0),
    RED=        LabelAttrs("Red",       1),
    ORANGE=     LabelAttrs("Orange",    2),
    YELLOW=     LabelAttrs("Yellow",    3),
    GREEN=      LabelAttrs("Green",     4),
    BLUE=       LabelAttrs("Blue",      5),
    PURPLE=     LabelAttrs("Purple",    6),
    GRAY=       LabelAttrs("Gray",      7)
)
label_num_to_label = dict((l.num, l) for l in Label.__values__)

# High-level iterface to the Papers2 database. Unless otherwise noted,
# query methods return a Query object, which can either be iterated 
# over or all rows can be fetched by calling the .all() method.
class Papers2(object):
    def __init__(self, folder="~/Papers2"):
        db = os.path.abspath(os.path.expanduser(os.path.join(
            folder, "Library.papers2", "Database.papersdb")))
        self.engine = create_engine(f"sqlite:///{os.path.abspath(db)}")
        self.folder = folder
        self.schema = automap_base()
        self.schema.prepare(self.engine, reflect=True)
        self._session = None
        self._cache = dict(
            bundle={}
        )
    
    def close(self):
        if self._session is not None:
            self._session.close()
    
    def get_session(self):
        if self._session is None:
            self._session = Session(self.engine)
        return self._session
    
    def get_table(self, name):
        return self.schema.classes.get(name)
    
    # Get all publications matching specified criteria.
    def get_publications(self, row_ids=None, author=None, types=None,
            include_deleted=False, include_duplicates=True, include_manuscripts=False):
        Publication = self.get_table("Publication")
        #criteria = [   #this would exclude anything that hasn't been cited...useful to record, perhaps--we'll add a tag?
        #    Publication.citekey != None,
        #    Publication.imported_date != None
        #]
        criteria = []

        #TODO Ideas here: put rating into zotero Extras so can sort by in list
        # put original date added to papers into zotero.accessedDate
        # tags are in pub.tag_string
        # how about summary? user_label?
        # if has citekey include tag: selfCited
        
        if row_ids is not None:
            criteria.append(Publication.ROWID.in_(row_ids))

        if author is not None:
            criteria.append(Publication.full_author_string.icontains(author))
        
        if types is not None:
            types = list(t.id for t in types)
            criteria.append(Publication.subtype.in_(types))
        else:
            criteria.append(Publication.subtype.in_(list(pub_type_id_to_pub_type.keys())))
        
        if not include_deleted:
            criteria.append(Publication.marked_deleted == False)
        if not include_duplicates:
            criteria.append(Publication.marked_duplicate == False)
        if not include_manuscripts:
            criteria.append(Publication.manuscript == False)
            
        q = self.get_session().query(Publication)
        if len(criteria) > 0:
            q = q.filter(*criteria)
        return q
    
    # Get a single publication by ID. Query is executed and
    # single result is returned.
    def get_publication(self, pub_id):
        Publication = self.get_table("Publication")
        return self.get_session().query(Publication
            ).filter(Publication.ROWID == pub_id
            ).one()

    def delete_publication(self, pub):
        self.get_session().delete(pub)
        self.get_session().commit()

    # ooh, this is how chapters are linked to books
    def get_bundle(self, pub):
        try:
            bundle_id = int(pub.bundle)
        except:
            return None
        if pub.bundle not in self._cache['bundle']:
            bundle = self.get_publication(bundle_id)
            self._cache['bundle'][pub.bundle] = bundle
        return self._cache['bundle'][pub.bundle]
        
    # Get the PubType name for a publication subtype code (see PubType enum)
    def get_pub_type(self, pub):
        return pub_type_id_to_pub_type[pub.subtype]
    
    def get_label_name(self, pub):
        return label_num_to_label[pub.label].name
    
    # Get authors for a publication, in order
    def get_pub_authors(self, pub):
        Author = self.get_table("Author")
        OrderedAuthor = self.get_table("OrderedAuthor")
        return self.get_session().query(
                Author.prename.label('prename'),
                Author.surname.label('surname'),
                Author.initial.label('initial'),
                Author.fullname.label('fullname'),
                Author.affiliation.label('affiliation'),
                Author.institutional.label('institutional'),
                OrderedAuthor.type.label('type')
            ).join(OrderedAuthor, Author.ROWID == OrderedAuthor.author_id
            ).filter(OrderedAuthor.object_id == pub.ROWID
            ).order_by(OrderedAuthor.priority)
    
    # Returns SyncEvents of the given source type as a list of IDs
    def get_identifiers(self, pub, id_source):
        SyncEvent = self.get_table("SyncEvent")
        return self.get_session().query(SyncEvent).filter(
            SyncEvent.device_id == pub.uuid,
            SyncEvent.source_id == id_source)
    
    # Returns SyncEvents with remote_ids like urls ('http%'),
    # ordered by most recent
    def get_urls(self, pub):
        SyncEvent = self.get_table("SyncEvent")
        return self.get_session().query(SyncEvent
            ).filter(
                SyncEvent.device_id == pub.uuid,
                SyncEvent.remote_id.like("http%")
            ).order_by(SyncEvent.updated_at.desc())
    
    # Get all attachments, with the primary attachment first.
    # Note that this does not return a query object, but
    # instead an iterator over (path, mime_type) tuples.
    def get_attachments(self, pub):
        PDF = self.get_table("PDF")
        attachments = self.get_session().query(PDF
            ).filter(PDF.object_id == pub.ROWID
            ).order_by(PDF.is_primary.desc())
        # resolve relative path names, but also retain item type to be able to properly translate to base folder
        return ((os.path.join(self.folder, a.path), a.mime_type, self.get_pub_type(pub)) for a in attachments if a.path is not None)
    
    def get_keywords(self, pub, kw_type=None):
        Keyword = self.get_table("Keyword")
        KeywordItem = self.get_table("KeywordItem")
        q = self.get_session().query(Keyword
            ).join(KeywordItem, Keyword.ROWID == KeywordItem.keyword_id
            ).filter(KeywordItem.object_id == pub.ROWID)
        if kw_type is not None:
            q = q.filter(KeywordItem.type == kw_type)
        return q
    
    def get_collections(self, pub=None):
        Collection = self.get_table("Collection")
        q = self.get_session().query(Collection)
        if pub is not None:
            CollectionItem = self.get_table("CollectionItem")
            q = q.join(CollectionItem, Collection.ROWID == CollectionItem.collection
                ).filter(CollectionItem.object_id == pub.ROWID)
        return q.filter(Collection.type.in_((0,5)))
    
    def get_reviews(self, pub, mine_only=True):
        Review = self.get_table("Review")
        q = self.get_session().query(Review
            ).filter(Review.object_id == pub.ROWID)
        if mine_only:
            q = q.filter(Review.is_mine == 1)
        return q