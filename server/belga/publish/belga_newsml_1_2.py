# -*- coding: utf-8; -*-
#
# This file is part of Superdesk.
#
# Copyright 2013, 2014 Sourcefabric z.u. and contributors.
#
# For the full copyright and license information, please see the
# AUTHORS and LICENSE files distributed with this source code, or
# at https://www.sourcefabric.org/superdesk/license

import html
from copy import deepcopy
import logging
from datetime import datetime
from lxml import etree
from lxml.etree import SubElement
from eve.utils import config
from flask import current_app as app
import superdesk
from superdesk.utc import utcnow
from superdesk.errors import FormatterError
from superdesk.publish.formatters.newsml_g2_formatter import XML_LANG
from superdesk.publish.formatters import NewsML12Formatter
from superdesk.metadata.item import ITEM_TYPE, CONTENT_TYPE, EMBARGO, GUID_FIELD

from apps.archive.common import get_utc_schedule

logger = logging.getLogger(__name__)


class BelgaNewsML12Formatter(NewsML12Formatter):
    """
    Belga News ML 1.2 1.2 Formatter
    """

    ENCODING = "ISO-8859-15"
    XML_ROOT = '<?xml version="1.0" encoding="{}"?>'.format(ENCODING)
    DATETIME_FORMAT = '%Y%m%dT%H%M%S'
    BELGA_TEXT_PROFILE = 'belga_text'

    def format(self, article, subscriber, codes=None):
        """
        Create article in Belga NewsML 1.2 format

        :param dict article:
        :param dict subscriber:
        :param list codes:
        :return [(int, str)]: return a List of tuples. A tuple consist of
            publish sequence number and formatted article string.
        :raises FormatterError: if the formatter fails to format an article
        """

        try:
            # pub_seq_num = superdesk.get_resource_service('subscribers').generate_sequence_number(subscriber)
            pub_seq_num = 11111
            self._newsml = etree.Element('NewsML')
            self._article = article
            self._now = utcnow()
            self._string_now = self._now.strftime(self.DATETIME_FORMAT)
            self._duid = self._article[GUID_FIELD]

            self._format_catalog()
            self._format_newsenvelope()
            self._format_newsitem()

            xml_string = self.XML_ROOT + '\n' + etree.tostring(self._newsml, pretty_print=True).decode('utf-8')

            return [(pub_seq_num, xml_string)]
        except Exception as ex:
            raise FormatterError.newml12FormatterError(ex, subscriber)

    def can_format(self, format_type, article):
        """
        Test if the article can be formatted to Belga NewsML 1.2 or not.

        :param str format_type:
        :param dict article:
        :return: True if article can formatted else False
        """

        if format_type == 'belganewsml12':
            if article[ITEM_TYPE] == CONTENT_TYPE.TEXT and article.get('profile') == self.BELGA_TEXT_PROFILE:
                return True
        return False

    def _format_catalog(self):
        """Creates Catalog and add it to `NewsML` container."""
        SubElement(
            self._newsml, 'Catalog',
            {'Href': 'http://www.belga.be/dtd/BelgaCatalog.xml'}
        )

    def _format_newsenvelope(self):
        """Creates NewsEnvelope and add it to `NewsML` container."""

        newsenvelope = SubElement(self._newsml, 'NewsEnvelope')
        SubElement(newsenvelope, 'DateAndTime').text = self._string_now
        SubElement(newsenvelope, 'NewsService', {'FormalName': ''})
        SubElement(newsenvelope, 'NewsProduct', {'FormalName': ''})

    def _format_newsitem(self):
        """Creates NewsItem and add it to `NewsML` container."""

        newsitem = SubElement(self._newsml, 'NewsItem')
        self._format_identification(newsitem)
        self._format_newsmanagement(newsitem)
        self._format_newscomponent_1_level(newsitem)

    def _format_identification(self, newsitem):
        """
        Creates the Identification element and add it to `newsitem`
        :param Element newsitem:
        """

        identification = SubElement(newsitem, 'Identification')
        news_identifier = SubElement(identification, 'NewsIdentifier')
        SubElement(news_identifier, 'ProviderId').text = app.config['NEWSML_PROVIDER_ID']
        SubElement(news_identifier, 'DateId').text = self._get_formatted_datetime(self._article.get('firstcreated'))
        SubElement(news_identifier, 'NewsItemId').text = self._duid
        revision = self._process_revision(self._article)
        SubElement(news_identifier, 'RevisionId', attrib=revision).text = str(self._article.get(config.VERSION, ''))
        SubElement(news_identifier, 'PublicIdentifier').text = self._generate_public_identifier(
            self._article[config.ID_FIELD],
            self._article.get(config.VERSION, ''),
            revision.get('Update', '')
        )

    def _format_newsmanagement(self, newsitem):
        """
        Creates the NewsManagement element and add it to `newsitem`
        :param Element newsitem:
        """
        news_management = SubElement(newsitem, 'NewsManagement')
        SubElement(news_management, 'NewsItemType', {'FormalName': 'News'})
        SubElement(
            news_management, 'FirstCreated'
        ).text = self._get_formatted_datetime(self._article.get('firstcreated'))
        SubElement(
            news_management, 'ThisRevisionCreated'
        ).text = self._get_formatted_datetime(self._article['versioncreated'])

        if self._article.get(EMBARGO):
            SubElement(news_management, 'Status', {'FormalName': 'Embargoed'})
            status_will_change = SubElement(news_management, 'StatusWillChange')
            SubElement(
                status_will_change, 'FutureStatus',
                {'FormalName': self._article.get('pubstatus', '').upper()}
            )
            SubElement(
                status_will_change, 'DateAndTime'
            ).text = get_utc_schedule(self._article, EMBARGO).isoformat()
        else:
            SubElement(
                news_management, 'Status',
                {'FormalName': self._article.get('pubstatus', '').upper()}
            )

    def _format_newscomponent_1_level(self, newsitem):
        """
        Creates the NewsComponent element and add it to `newsitem`
        :param Element newsitem:
        """

        newscomponent_1_level = SubElement(
            newsitem, 'NewsComponent',
            {'Duid': self._duid, XML_LANG: self._article.get('language')}
        )
        newslines = SubElement(newscomponent_1_level, 'NewsLines')
        SubElement(newslines, 'HeadLine').text = self._article.get('headline', '')
        SubElement(newscomponent_1_level, 'AdministrativeMetadata')
        descriptivemetadata = SubElement(newscomponent_1_level, 'DescriptiveMetadata')
        genre_formalname = ''
        for subject in self._article.get('subject', []):
            if subject['scheme'] == 'genre':
                genre_formalname = subject['qcode']
                break
        SubElement(
            descriptivemetadata, 'Genre',
            {'FormalName': genre_formalname}
        )

        self._format_newscomponent_2_level(newscomponent_1_level)

    def _format_newscomponent_2_level(self, newscomponent_1_level):
        """
        Creates the NewsComponent of a 2nd level element and add it to `newscomponent_1_level`
        :param Element newscomponent_1_level:
        """

        _type = self._article.get('type')
        _profile = self._article.get('profile')

        self._format_belga_text(newscomponent_1_level)
        self._format_belga_urls(newscomponent_1_level)
        self._format_media(newscomponent_1_level)

    def _format_belga_text(self, newscomponent_1_level):
        """
        Creates a NewsComponent of a 2nd level with information related to `belga_text` content profile.
        :param Element newscomponent_1_level:
        """

        newscomponent_2_level = SubElement(
            newscomponent_1_level, 'NewsComponent',
            {XML_LANG: self._article.get('language')}
        )

        # Role
        SubElement(newscomponent_2_level, 'Role', {'FormalName': self.BELGA_TEXT_PROFILE})
        # NewsLines
        self._format_newslines(newscomponent_2_level)
        # AdministrativeMetadata
        self._format_administrative_metadata(newscomponent_2_level, item=self._article)
        # DescriptiveMetadata
        self._format_descriptive_metadata(newscomponent_2_level, item=self._article)
        # NewsComponent 3rd level
        self._format_newscomponent_3_level(newscomponent_2_level)

    def _format_belga_urls(self, newscomponent_1_level):
        """
        Creates a NewsComponents of a 2nd level with URLs from `belga-text`.
        :param Element newscomponent_1_level:
        """

        for belga_url in self._article.get('extra', {}).get('belga-url', []):
            newscomponent_2_level = SubElement(
                newscomponent_1_level, 'NewsComponent',
                {XML_LANG: self._article.get('language')}
            )
            SubElement(newscomponent_2_level, 'Role', {'FormalName': 'URL'})
            newslines = SubElement(newscomponent_2_level, 'NewsLines')
            SubElement(newslines, 'DateLine')
            SubElement(newslines, 'CreditLine').text = self._article.get('byline')
            SubElement(newslines, 'HeadLine').text = belga_url.get('description')
            SubElement(newslines, 'CopyrightLine').text = self._article.get('copyrightholder')
            self._format_administrative_metadata(newscomponent_2_level, item=self._article)
            self._format_descriptive_metadata(newscomponent_2_level, item=self._article)

            for role, key in (('Title', 'description'), ('Locator', 'url')):
                newscomponent_3_level = SubElement(
                    newscomponent_2_level, 'NewsComponent',
                    {XML_LANG: self._article.get('language')}
                )
                SubElement(newscomponent_3_level, 'Role', {'FormalName': role})
                SubElement(
                    SubElement(newscomponent_3_level, 'DescriptiveMetadata'),
                    'Property',
                    {'FormalName': 'ComponentClass', 'Value': 'Text'}
                )
                contentitem = SubElement(newscomponent_3_level, 'ContentItem')
                SubElement(contentitem, 'Format', {'FormalName': 'Text'})
                SubElement(contentitem, 'DataContent').text = belga_url.get(key)
                characteristics = SubElement(contentitem, 'Characteristics')
                # string's length is used in original belga's newsml
                SubElement(characteristics, 'SizeInBytes').text = str(len(belga_url.get(key)))
                SubElement(characteristics, 'Property', {'FormalName': 'maxCharCount', 'Value': '0'})

    def _format_media(self, newscomponent_1_level):
        """
        Formats images from body, related images, galleries.
        :param Element newscomponent_1_level:
        """

        associations = self._article.get('associations', {})

        # NOTE:
        # - Associated items with type `picture` (images from body / related images / related gallery) will be
        #   converted to Belga360 NewsML representation as an `Image`.
        # - Associated items with type `graphic` (belga coverage) will be converted to Belga360 NewsML representation
        #   as an `Gallery`.
        # - Associated items with type `audio` will be converted to Belga360 NewsML representation
        #   as an `Audio`.
        # - Associated items with type `video` will be converted to Belga360 NewsML representation
        #   as an `Video`.

        # PICTUTES
        # get all associated docs with type `picture` where `renditions` are already IN the doc.
        pictures = [
            associations[i] for i in associations
            if associations[i]
            and associations[i]['type'] == 'picture'
            and 'renditions' in self._article['associations'][i]
        ]
        # get all associated docs _ids with type `picture` where `renditions` are NOT IN the doc
        pictures_ids = [
            associations[i]['_id'] for i in associations
            if associations[i]
            and associations[i]['type'] == 'picture'
            and 'renditions' not in self._article['associations'][i]
        ]
        # fetch associated docs by _id
        if pictures_ids:
            archive_service = superdesk.get_resource_service('archive')
            pictures += list(archive_service.find({
                '_id': {'$in': pictures_ids}}
            ))
        # format pictures
        formatted_ids = []
        for picture in pictures:
            if picture['_id'] not in formatted_ids:
                formatted_ids.append(picture['_id'])
                self._format_picture(newscomponent_1_level, picture)

        # COVERAGES
        # get all associated docs with type `graphic` where `renditions` are already IN the doc.
        coverages = [
            associations[i] for i in associations
            if associations[i]
            and associations[i]['type'] == 'graphic'
            and 'renditions' in self._article['associations'][i]
        ]
        # get all associated docs _ids with type `graphic` where `renditions` are NOT IN the doc
        coverages_ids = [
            associations[i]['_id'] for i in associations
            if associations[i]
            and associations[i]['type'] == 'graphic'
            and 'renditions' not in self._article['associations'][i]
        ]
        # fetch associated docs by _id
        if coverages_ids:
            archive_service = superdesk.get_resource_service('archive')
            coverages += list(archive_service.find({
                '_id': {'$in': pictures_ids}}
            ))

        # format coverages
        formatted_ids = []
        for coverage in coverages:
            if coverage['_id'] not in formatted_ids:
                formatted_ids.append(coverage['_id'])
                self._format_coverage(newscomponent_1_level, coverage)

        # AUDIOS
        # get all associated docs with type `audio` where `renditions` are already IN the doc.
        audios = [
            associations[i] for i in associations
            if associations[i]
               and associations[i]['type'] == 'audio'
               and 'renditions' in self._article['associations'][i]
        ]
        # get all associated docs _ids with type `graphic` where `renditions` are NOT IN the doc
        audios_ids = [
            associations[i]['_id'] for i in associations
            if associations[i]
               and associations[i]['type'] == 'audio'
               and 'renditions' not in self._article['associations'][i]
        ]
        # fetch associated docs by _id
        if audios_ids:
            archive_service = superdesk.get_resource_service('archive')
            audios += list(archive_service.find({
                '_id': {'$in': pictures_ids}}
            ))

        # format audio
        formatted_ids = []
        for audio in audios:
            if audio['_id'] not in formatted_ids:
                formatted_ids.append(audio['_id'])
                self._format_audio(newscomponent_1_level, audio)

        # VIDEOS
        # get all associated docs with type `video` where `renditions` are already IN the doc.
        videos = [
            associations[i] for i in associations
            if associations[i]
               and associations[i]['type'] == 'video'
               and 'renditions' in self._article['associations'][i]
        ]
        # get all associated docs _ids with type `graphic` where `renditions` are NOT IN the doc
        videos_ids = [
            associations[i]['_id'] for i in associations
            if associations[i]
               and associations[i]['type'] == 'video'
               and 'renditions' not in self._article['associations'][i]
        ]
        # fetch associated docs by _id
        if videos_ids:
            archive_service = superdesk.get_resource_service('archive')
            videos += list(archive_service.find({
                '_id': {'$in': pictures_ids}}
            ))

        # format video
        formatted_ids = []
        for video in videos:
            if video['_id'] not in formatted_ids:
                formatted_ids.append(video['_id'])
                self._format_video(newscomponent_1_level, video)

    def _format_picture(self, newscomponent_1_level, picture):
        """
        Creates a NewsComponent of a 2nd level with picture from `belga-text` article.
        :param Element newscomponent_1_level:
        :param dict picture:
        """

        # NewsComponent
        newscomponent_2_level = SubElement(newscomponent_1_level, 'NewsComponent')
        if picture.get(GUID_FIELD):
            newscomponent_2_level.attrib['Duid'] = picture.get(GUID_FIELD)
        if picture.get('language'):
            newscomponent_2_level.attrib[XML_LANG] = picture.get('language')
        # Role
        SubElement(newscomponent_2_level, 'Role', {'FormalName': 'Picture'})
        # NewsLines
        self._format_media_newslines(newscomponent_2_level, item=picture)
        # AdministrativeMetadata
        self._format_administrative_metadata(newscomponent_2_level, item=picture)
        self._format_descriptive_metadata(newscomponent_2_level, item=picture)

        for role, key in (('Title', 'headline'), ('Caption', 'description_text')):
            newscomponent_3_level = SubElement(newscomponent_2_level, 'NewsComponent')
            if picture.get('language'):
                newscomponent_3_level.attrib[XML_LANG] = picture.get('language')
            SubElement(newscomponent_3_level, 'Role', {'FormalName': role})
            SubElement(
                SubElement(newscomponent_3_level, 'DescriptiveMetadata'),
                'Property',
                {'FormalName': 'ComponentClass', 'Value': 'Text'}
            )
            contentitem = SubElement(newscomponent_3_level, 'ContentItem')
            SubElement(contentitem, 'Format', {'FormalName': 'Text'})
            SubElement(contentitem, 'DataContent').text = picture.get(key)
            characteristics = SubElement(contentitem, 'Characteristics')
            # string's length is used in original belga's newsml
            SubElement(characteristics, 'SizeInBytes').text = str(len(picture.get(key)))
            SubElement(characteristics, 'Property', {'FormalName': 'maxCharCount', 'Value': '0'})

        # original, thumbnail, preview
        for role, key in (('Image', 'original'), ('Thumbnail', 'thumbnail'), ('Preview', 'viewImage')):
            if key not in picture['renditions']:
                continue
            newscomponent_3_level = SubElement(newscomponent_2_level, 'NewsComponent')
            if picture.get('language'):
                newscomponent_3_level.attrib[XML_LANG] = picture.get('language')

            SubElement(newscomponent_3_level, 'Role', {'FormalName': role})
            SubElement(
                SubElement(newscomponent_3_level, 'DescriptiveMetadata'),
                'Property',
                {'FormalName': 'ComponentClass', 'Value': 'Image'}
            )
            self._format_media_contentitem(newscomponent_3_level, rendition=picture['renditions'][key])

    def _format_coverage(self, newscomponent_1_level, coverage):
        """
        Creates a NewsComponent of a 2nd level with coverage item from an article.
        :param Element newscomponent_1_level:
        :param dict coverage:
        """

        newscomponent_2_level = SubElement(newscomponent_1_level, 'NewsComponent')
        if coverage.get(GUID_FIELD):
            newscomponent_2_level.attrib['Duid'] = coverage.get(GUID_FIELD)
        if coverage.get('language'):
            newscomponent_2_level.attrib[XML_LANG] = coverage.get('language')
        SubElement(newscomponent_2_level, 'Role', {'FormalName': 'Gallery'})
        self._format_media_newslines(newscomponent_2_level, item=coverage)
        self._format_administrative_metadata(newscomponent_2_level, item=coverage)
        self._format_descriptive_metadata(newscomponent_2_level, item=coverage)

        for role, key in (('Title', 'headline'), ('Caption', 'description_text')):
            newscomponent_3_level = SubElement(newscomponent_2_level, 'NewsComponent')
            if coverage.get('language'):
                newscomponent_3_level.attrib[XML_LANG] = coverage.get('language')
            SubElement(newscomponent_3_level, 'Role', {'FormalName': role})
            SubElement(
                SubElement(newscomponent_3_level, 'DescriptiveMetadata'),
                'Property',
                {'FormalName': 'ComponentClass', 'Value': 'Text'}
            )
            contentitem = SubElement(newscomponent_3_level, 'ContentItem')
            SubElement(contentitem, 'Format', {'FormalName': 'Text'})
            SubElement(contentitem, 'DataContent').text = coverage.get(key)
            characteristics = SubElement(contentitem, 'Characteristics')
            # string's length is used in original belga's newsml
            SubElement(characteristics, 'SizeInBytes').text = str(len(coverage.get(key)))
            SubElement(characteristics, 'Property', {'FormalName': 'maxCharCount', 'Value': '0'})

        newscomponent_3_level = SubElement(newscomponent_2_level, 'NewsComponent')
        if coverage.get(GUID_FIELD):
            newscomponent_3_level.attrib['Duid'] = coverage.get(GUID_FIELD)
        if coverage.get('language'):
            newscomponent_3_level.attrib[XML_LANG] = coverage.get('language')

        SubElement(newscomponent_3_level, 'Role', {'FormalName': 'Component'})
        SubElement(
            SubElement(newscomponent_3_level, 'DescriptiveMetadata'),
            'Property',
            {'FormalName': 'ComponentClass', 'Value': 'Image'}
        )
        self._format_media_contentitem(newscomponent_3_level, rendition=coverage['renditions']['original'])

    def _format_audio(self, newscomponent_1_level, audio):
        """
        Creates a NewsComponent of a 2nd level with audio item from an article.
        :param Element newscomponent_1_level:
        :param dict audio:
        """

        newscomponent_2_level = SubElement(newscomponent_1_level, 'NewsComponent')
        if audio.get(GUID_FIELD):
            newscomponent_2_level.attrib['Duid'] = audio.get(GUID_FIELD)
        if audio.get('language'):
            newscomponent_2_level.attrib[XML_LANG] = audio.get('language')
        SubElement(newscomponent_2_level, 'Role', {'FormalName': 'Audio'})
        self._format_media_newslines(newscomponent_2_level, item=audio)
        self._format_administrative_metadata(newscomponent_2_level, item=audio)
        self._format_descriptive_metadata(newscomponent_2_level, item=audio)

        for role, key in (('Title', 'headline'), ('Body', 'description_text')):
            newscomponent_3_level = SubElement(newscomponent_2_level, 'NewsComponent')
            if audio.get('language'):
                newscomponent_3_level.attrib[XML_LANG] = audio.get('language')
            SubElement(newscomponent_3_level, 'Role', {'FormalName': role})
            SubElement(
                SubElement(newscomponent_3_level, 'DescriptiveMetadata'),
                'Property',
                {'FormalName': 'ComponentClass', 'Value': 'Text'}
            )
            contentitem = SubElement(newscomponent_3_level, 'ContentItem')
            SubElement(contentitem, 'Format', {'FormalName': 'Text'})
            SubElement(contentitem, 'DataContent').text = audio.get(key)
            characteristics = SubElement(contentitem, 'Characteristics')
            # string's length is used in original belga's newsml
            SubElement(characteristics, 'SizeInBytes').text = str(len(audio.get(key)))
            SubElement(characteristics, 'Property', {'FormalName': 'maxCharCount', 'Value': '0'})

        # sound
        newscomponent_3_level = SubElement(newscomponent_2_level, 'NewsComponent')
        if audio.get(GUID_FIELD):
            newscomponent_3_level.attrib['Duid'] = audio.get(GUID_FIELD)
        if audio.get('language'):
            newscomponent_3_level.attrib[XML_LANG] = audio.get('language')

        SubElement(newscomponent_3_level, 'Role', {'FormalName': 'Sound'})
        SubElement(
            SubElement(newscomponent_3_level, 'DescriptiveMetadata'),
            'Property',
            {'FormalName': 'ComponentClass', 'Value': 'Audio'}
        )
        self._format_media_contentitem(newscomponent_3_level, rendition=audio['renditions']['original'])

    def _format_video(self, newscomponent_1_level, video):
        """
        Creates a NewsComponent of a 2nd level with video item from an article.
        :param Element newscomponent_1_level:
        :param dict audio:
        """

        newscomponent_2_level = SubElement(newscomponent_1_level, 'NewsComponent')
        if video.get(GUID_FIELD):
            newscomponent_2_level.attrib['Duid'] = video.get(GUID_FIELD)
        if video.get('language'):
            newscomponent_2_level.attrib[XML_LANG] = video.get('language')
        SubElement(newscomponent_2_level, 'Role', {'FormalName': 'Video'})
        self._format_media_newslines(newscomponent_2_level, item=video)
        self._format_administrative_metadata(newscomponent_2_level, item=video)
        self._format_descriptive_metadata(newscomponent_2_level, item=video)

        for role, key in (('Title', 'headline'), ('Body', 'description_text')):
            newscomponent_3_level = SubElement(newscomponent_2_level, 'NewsComponent')
            if video.get('language'):
                newscomponent_3_level.attrib[XML_LANG] = video.get('language')
            SubElement(newscomponent_3_level, 'Role', {'FormalName': role})
            SubElement(
                SubElement(newscomponent_3_level, 'DescriptiveMetadata'),
                'Property',
                {'FormalName': 'ComponentClass', 'Value': 'Text'}
            )
            contentitem = SubElement(newscomponent_3_level, 'ContentItem')
            SubElement(contentitem, 'Format', {'FormalName': 'Text'})
            SubElement(contentitem, 'DataContent').text = video.get(key)
            characteristics = SubElement(contentitem, 'Characteristics')
            # string's length is used in original belga's newsml
            SubElement(characteristics, 'SizeInBytes').text = str(len(video.get(key)))
            SubElement(characteristics, 'Property', {'FormalName': 'maxCharCount', 'Value': '0'})

        # sound
        newscomponent_3_level = SubElement(newscomponent_2_level, 'NewsComponent')
        if video.get(GUID_FIELD):
            newscomponent_3_level.attrib['Duid'] = video.get(GUID_FIELD)
        if video.get('language'):
            newscomponent_3_level.attrib[XML_LANG] = video.get('language')

        SubElement(newscomponent_3_level, 'Role', {'FormalName': 'Clip'})
        SubElement(
            SubElement(newscomponent_3_level, 'DescriptiveMetadata'),
            'Property',
            {'FormalName': 'ComponentClass', 'Value': 'Audio'}
        )
        self._format_media_contentitem(newscomponent_3_level, rendition=video['renditions']['original'])

    def _format_media_contentitem(self, newscomponent_3_level, rendition):
        """
        Creates a ContentItem for media item.
        :param Element newscomponent_3_level:
        :param dict rendition:
        """
        contentitem = SubElement(
            newscomponent_3_level, 'ContentItem',
            {'Href': r'{}'.format(rendition['href'])}
        )
        SubElement(contentitem, 'Format', {'FormalName': rendition['href'].rsplit('.', 1)[-1]})
        if rendition.get('mimetype'):
            SubElement(contentitem, 'MimeType', {'FormalName': rendition['mimetype']})
        characteristics = SubElement(contentitem, 'Characteristics')

        if rendition.get('media'):
            SubElement(
                characteristics, 'SizeInBytes'
            ).text = str(
                # str is used in original belga's newsml
                app.media.get(rendition['media']).metadata['length']
            )
        if rendition.get('width'):
            SubElement(
                characteristics, 'Property',
                {'FormalName': 'Width', 'Value': str(rendition['width'])}
            )
        if rendition.get('height'):
            SubElement(
                characteristics, 'Property',
                {'FormalName': 'Height', 'Value': str(rendition['height'])}
            )

    def _format_media_newslines(self, newscomponent_2_level, item):
        """
        Creates the NewsLines element for media item and add it to `newscomponent_2_level`
        :param Element newscomponent_2_level:
        :param dict item:
        """
        newslines = SubElement(newscomponent_2_level, 'NewsLines')
        SubElement(newslines, 'DateLine')
        SubElement(newslines, 'CreditLine').text = item.get('creditline', item.get('byline'))
        SubElement(newslines, 'HeadLine').text = item.get('headline')
        SubElement(newslines, 'CopyrightLine').text = item.get('copyrightholder')
        SubElement(newslines, 'KeywordLine').text = item.get('extra', {}).get('belga-keywords')

    def _format_newslines(self, newscomponent_2_level):
        """
        Creates the NewsLines element for text item and add it to `newscomponent_2_level`
        :param Element newscomponent_2_level:
        """
        newslines = SubElement(newscomponent_2_level, 'NewsLines')
        SubElement(newslines, 'DateLine')
        SubElement(newslines, 'CreditLine').text = self._article.get('byline')
        SubElement(newslines, 'HeadLine').text = self._article.get('headline')
        SubElement(newslines, 'CopyrightLine').text = self._article.get('copyrightholder')
        for keyword in self._article.get('keywords', []):
            SubElement(newslines, 'KeywordLine').text = keyword
        newsline = SubElement(newslines, 'NewsLine')
        SubElement(newsline, 'NewsLineType', {'FormalName': self._article.get('line_type', '')})
        SubElement(newsline, 'NewsLineText').text = self._article.get('line_text')

    def _format_administrative_metadata(self, newscomponent_2_level, item):
        """
        Creates the AdministrativeMetadata element and add it to `newscomponent_2_level`
        :param Element newscomponent_2_level:
        :param dict item:
        """

        administrative_metadata = SubElement(newscomponent_2_level, 'AdministrativeMetadata')
        SubElement(
            SubElement(administrative_metadata, 'Provider'),
            'Party',
            {'FormalName': item.get('line_type', '')}
        )
        creator = SubElement(administrative_metadata, 'Creator')

        if item['type'] == CONTENT_TYPE.PICTURE:
            authors = (item['original_creator'],) if item.get('original_creator') else tuple()
        else:
            authors = item.get('authors', tuple())
        for author in authors:
            author = self._get_author_info(author)
            SubElement(
                creator, 'Party',
                {'FormalName': author['name'], 'Topic': author['role']}
            )
        if 'contributor' in item.get('administrative', {}):
            SubElement(
                SubElement(administrative_metadata, 'Contributor'), 'Party',
                {'FormalName': item['administrative']['contributor']}
            )
        if 'validator' in item.get('administrative', {}):
            SubElement(
                administrative_metadata, 'Property',
                {'FormalName': 'Validator', 'Value': item['administrative']['validator']}
            )
        if 'validation_date' in item.get('administrative', {}):
            SubElement(
                administrative_metadata, 'Property',
                {'FormalName': 'ValidationDate', 'Value': item['administrative']['validation_date']}
            )
        if 'foreign_id' in item.get('administrative', {}):
            SubElement(
                administrative_metadata, 'Property',
                {'FormalName': 'ForeignId', 'Value': item['administrative']['foreign_id']}
            )
        if 'priority' in item:
            SubElement(
                administrative_metadata, 'Property',
                {'FormalName': 'Priority', 'Value': str(item['priority'])}
            )
        SubElement(
            administrative_metadata,
            'Property',
            {'FormalName': 'NewsObjectId', 'Value': item[GUID_FIELD]}
        )
        property_newspackage = SubElement(
            administrative_metadata, 'Property',
            {'FormalName': 'NewsPackage'}
        )
        for subject in item.get('subject', []):
            if subject['scheme'] == 'news_services':
                SubElement(
                    property_newspackage, 'Property',
                    {'FormalName': 'NewsService', 'Value': subject['qcode']}
                )
            elif subject['scheme'] == 'news_products':
                SubElement(
                    property_newspackage, 'Property',
                    {'FormalName': 'NewsProduct', 'Value': subject['qcode']}
                )
        if 'source' in item:
            SubElement(
                SubElement(administrative_metadata, 'Source'),
                'Party',
                {'FormalName': item['source']}
            )

    def _format_descriptive_metadata(self, newscomponent_2_level, item):
        """
        Creates the DescriptiveMetadata element and add it to `newscomponent_2_level`
        :param Element newscomponent_2_level:
        :param dict item:
        """

        descriptive_metadata = SubElement(
            newscomponent_2_level, 'DescriptiveMetadata',
            {'DateAndTime': self._get_formatted_datetime(item['firstcreated'])}
        )
        SubElement(descriptive_metadata, 'SubjectCode')
        location = SubElement(descriptive_metadata, 'Location')

        city_property = SubElement(location, 'Property', {'FormalName': 'City'})
        if item.get('extra', {}).get('city'):
            city_property.set('Value', item['extra']['city'])

        country_property = SubElement(location, 'Property', {'FormalName': 'Country'})
        if item.get('extra', {}).get('country'):
            country_property.set('Value', item['extra']['country'])

        SubElement(location, 'Property', {'FormalName': 'CountryArea'})
        SubElement(location, 'Property', {'FormalName': 'WorldRegion'})

    def _format_newscomponent_3_level(self, newscomponent_2_level):
        """
        Creates the NewsComponent(s) of a 3rd level element and add it to `newscomponent_2_level`
        :param Element newscomponent_2_level:
        """

        # Title, Lead, Body
        for formalname, item_key in (('Body', 'body_html'), ('Title', 'headline'), ('Lead', 'abstract')):
            if self._article.get(item_key):
                newscomponent_3_level = SubElement(
                    newscomponent_2_level, 'NewsComponent',
                    {XML_LANG: self._article.get('language')}
                )
                # Role
                SubElement(newscomponent_3_level, 'Role', {'FormalName': formalname})
                # DescriptiveMetadata > Property
                SubElement(
                    SubElement(newscomponent_3_level, 'DescriptiveMetadata'),
                    'Property', {'FormalName': 'ComponentClass', 'Value': 'Text'}
                )
                # ContentItem
                contentitem = SubElement(newscomponent_3_level, 'ContentItem')
                SubElement(contentitem, 'Format', {'FormalName': 'Text'})
                text = html.escape(self._article.get(item_key))
                SubElement(contentitem, 'DataContent').text = text
                characteristics = SubElement(contentitem, 'Characteristics')
                # string's length is used in original belga's newsml
                SubElement(characteristics, 'SizeInBytes').text = str(len(text))
                SubElement(characteristics, 'Property', {'FormalName': 'maxCharCount', 'Value': '0'})

    def _get_author_info(self, author):
        author_info = {
            'name': '',
            'role': ''
        }
        users_service = superdesk.get_resource_service('users')

        if type(author) is str:
            author_id = author
            try:
                user = next(users_service.find({'_id': author_id}))
            except StopIteration:
                logger.warning("unknown user: {user_id}".format(user_id=author_id))
            else:
                if user.get('display_name'):
                    author_info['name'] = user.get('display_name')
                if user.get('role'):
                    roles_service = superdesk.get_resource_service('roles')
                    try:
                        role = next(roles_service.find({'_id': user['role']}))
                    except StopIteration:
                        logger.warning("unknown role: {role_id}".format(role_id=user['role']))
                    else:
                        author_info['role'] = role.get('author_role', '')
        else:
            author_info['name'] = author.get('sub_label', author['name'] if author.get('name') else '')
            author_info['role'] = author['role'] if author.get('role') else ''

            if 'parent' in author:
                try:
                    user = next(users_service.find({'_id': author['parent']}))
                except StopIteration:
                    logger.warning("unknown user: {user_id}".format(user_id=author['parent']))
                else:
                    if user.get('display_name'):
                        author_info['name'] = user.get('display_name')

        return author_info

    def _get_formatted_datetime(self, _datetime):
        if type(_datetime) is str:
            return datetime.strptime(_datetime, '%Y-%m-%dT%H:%M:%S+0000').strftime(self.DATETIME_FORMAT)
        else:
            return _datetime.strftime(self.DATETIME_FORMAT)
