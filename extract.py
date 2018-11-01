from lxml import html
from argparse import ArgumentParser
import base64
import hashlib
import logging
import os
import re
import requests
import shutil
import sys
import urlparse

FOLDERS_TO_CREATE = ['css', 'fonts', 'icons', 'images', 'js', 'other']
HEADER = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_4) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/65.0.3325.181 Safari/537.36"
}
TEMPLATE_FILE_NAME_HTML = "index.html"
TEMPLATE_FILE_NAME_FTL = "base-layout.ftl"
FTL_IMPORT_TAG = "<#include \"../include/imports.ftl\">\n"
WEBFILES_START_TAG_SEARCHREPLACE = "===webfiles_start_tag==="
WEBFILES_END_TAG_SEARCHREPLACE = "===webfiles_end_tag==="
WEBFILES_START_TAG = "<@hst.webfile path=\""
WEBFILES_END_TAG = "\"/>"

HST_WHITELIST_FILE_NAME = "hst-whitelist.txt"
HST_WHITELIST_PREAMBLE = """\
##########################################################################
#                                                                        #
#   This file must contain all files and folders that                    #
#   most be publicly available over http. Typically folders              #
#   that contain server side scripts, such a freemarker                  #
#   templates, should not be added as they in general should             #
#   not be publicly available.                                           #
#                                                                        #
#   The whitelisting is *relative* to the 'web file bundle root'         #
#   which is the folder in which this hst-whitelist.txt file is          #
#   located.                                                             #
#                                                                        #
#   Examples assuming the web file bundle root is 'site':                #
#                                                                        #
#   css/       : whitelists all descendant web files below 'site/css/'   #
#   common.js  : whitelists the file 'site/common.js'                    #
#                                                                        #
#   Note that the whitelisting is 'starts-with' based, thus for          #
#   example whitelisting 'css' without '/' behind it, whitelists all     #
#   files and folders that start with 'css'                              #
#                                                                        #
##########################################################################

"""

# initiate logger
logging.basicConfig()
logger = logging.getLogger(__name__)


# encapsulate the path to the web resource in the webfile tag so the link works directly in Hippo
# however, lxml will escape the <@hst.webfile tag, so put placeholders that will be searched & replaced later
# has to be in a separate method, otherwise path to css files will be incorrect for extraction of css web resources
def add_webfiles_tags_to_resource_path(resource_path):
    if not args.html:
        resource_path = WEBFILES_START_TAG_SEARCHREPLACE + resource_path + WEBFILES_END_TAG_SEARCHREPLACE
    return resource_path


# create folders for storing all web resources, categorized by type (CSS, fonts, etc.)
def create_folders(output_folder, folder_list):
    for folder in folder_list:
        folder_path = "%s/%s" % (output_folder, folder)
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)


# create hst-whitelist with all the folders being created
def create_whitelist(output_folder, folder_list):
    file_contents = HST_WHITELIST_PREAMBLE + "/\n".join(folder_list + [""])

    file_name = "%s/%s" % (output_folder, HST_WHITELIST_FILE_NAME)
    with open(file_name, 'w') as f:
        f.write(file_contents)


# download resource for URL, raise error if 404 or other error is returned
def download_resource(url, ext, save_path=None):
    # download resource
    try:
        # download as binary for images, icons and non-SVG fonts
        write_mode = select_folder(ext)[1]
        stream = False
        if write_mode == 'wb':
            stream = True

        logger.info("Downloading external resource with URL '%s'", url)
        response = requests.get(url, headers=HEADER, timeout=3, stream=stream)
        response.raise_for_status()

        # only use encoding for non-binary files
        if write_mode == 'w':
            if response.encoding:
                response = response.text.encode(response.encoding)
            else:
                response = response.text.encode('utf-8')

        # write resource if save_path is provided
        if save_path:
            logger.debug("Writing external resource as %s from URL '%s' to '%s'", write_mode, url, save_path)
            write_resource(response, write_mode, save_path)

        return response
    except requests.exceptions.HTTPError as e:
        logger.warn("HTTP Error for URL: %s, %s", url, e)
    except requests.exceptions.Timeout:
        logger.error("Error, request timed out for URL: %s", url)
    except requests.exceptions.RequestException as e:
        logger.error("Error '%s' for URL: %s", e, url)


# write resource to disk
def write_resource(response, write_mode, save_path):
    with open(save_path, write_mode) as f:
        # non-binaries
        if write_mode == "w":
            f.write(response)
        # binaries
        else:
            shutil.copyfileobj(response.raw, f)


# download web resource, determine full URL and save location
def save_resource(origin_url, url, save_folder):
    # get fully qualified URL, regardless if URL is a full URL, relative or absolute
    full_url = urlparse.urljoin(origin_url, url)

    # get filename and extension of resource
    file_name = urlparse.urlsplit(url).path.split('/')[-1]
    ext = file_name.split('.')[-1].lower()
    # add unique hash as suffix to filename in case there are web resources with duplicate names
    # since these are stored all in the same folder (no subfolders used), this prevents overwriting
    hasher = hashlib.sha1(full_url)
    file_name = "%s-%s.%s" % (file_name, base64.urlsafe_b64encode(hasher.digest()[0:5]).strip('='), ext)

    # determine which folder the resource should be saved to (image, font, etc.)
    folder = select_folder(ext)[0]
    resource_path = "%s/%s" % (folder, file_name)

    # do not download videos unless flag has been set
    if folder == 'videos' and not args.videos:
        return url

    # add save_folder to resource path to determine path for saving the resource
    save_path = "%s/%s" % (save_folder, resource_path)

    # only download if file is not already existing (has been downloaded before)
    # always download css files, because cannot resolve URLs in existing parsed css files
    if not os.path.isfile(save_path) or ext == "css":
        response = download_resource(full_url, ext, save_path)
        if not response:
            return url
    else:
        logger.info("File already exists: %s", save_path)

    return resource_path


# search CSS stylesheet (string) for web resources and download them
def save_resources_from_css(origin_url, stylesheet_string, save_folder, external):
    # check if a style element does not contain text so no exception is raised
    if stylesheet_string:
        # use regexp to search for url(...)
        pattern = re.compile(r'url\(([^)]*)\)')
        pos = 0
        url = pattern.search(stylesheet_string, pos)

        while url:
            # remove leading and trailing ' and "
            if url.group(1).startswith('\'') or url.group(1).startswith('"'):
                sanitized_url = url.group(1)[1:-1]
            else:
                sanitized_url = url.group(1)

            # check if URL is not null and does not contain binary data
            if sanitized_url and not sanitized_url.startswith('data:'):
                # save resource
                resource_path = save_resource(origin_url, sanitized_url, save_folder)
                # if external stylesheet, resources referenced (e.g. fonts) will be one folder up
                # so correct the path
                if external:
                    resource_path = "../%s" % resource_path
                # for internal/inline css, add the webfiles tags
                else:
                    resource_path = add_webfiles_tags_to_resource_path(resource_path)
                # replace url with new path
                stylesheet_string = stylesheet_string[:url.start(1)] + resource_path + stylesheet_string[url.end(1):]
                # update position for next search
                pos = url.start(1) + len(resource_path) + 1
            else:
                # update position for next search
                pos = url.end(0)

            # do new search
            url = pattern.search(stylesheet_string, pos)

    return stylesheet_string


# switch-case statement used by create_folders()
# returns tuples of folder and write-mode (binary, non-binary)
def select_folder(ext):
    return {
        'css': ('css', 'w'),
        'js': ('js', 'w'),
        # images
        'gif': ('images', 'wb'),
        'jpeg': ('images', 'wb'),
        'jpg': ('images', 'wb'),
        'png': ('images', 'wb'),
        # icons
        'ico': ('icons', 'wb'),
        # fonts
        'eot': ('fonts', 'wb'),
        'svg': ('fonts', 'w'),
        'ttf': ('fonts', 'wb'),
        'woff': ('fonts', 'wb'),
        'woff2': ('fonts', 'wb'),
        'other': ('other', 'w'),
        # videos
        'mp4': ('videos', 'wb'),
        'ogv': ('videos', 'wb'),
        'webm': ('videos', 'wb'),
        'mov': ('videos', 'wb'),
        # HTML fragments
        'htm': ('other', 'w'),
        'html': ('other', 'w'),
    }.get(ext, ('other', 'w'))


def main(url, save_folder):
    try:
        print("Extracting resources from {} to folder '{}'...".format(url, save_folder))
        if not args.supplied_html:
            # download resource from URL and parse HTML
            root = html.fromstring(download_resource(url, '.html'))
        else:
            if os.path.isfile(args.supplied_html):
                with open(args.supplied_html, 'r') as f:
                    supplied_html_file_contents = f.read()
                    root = html.fromstring(supplied_html_file_contents)
            else:
                logger.error("Could not supplied HTML file: %s", args.supplied_html)
                sys.exit()

        if root is not None:
            # prepare folders
            create_folders(save_folder, FOLDERS_TO_CREATE)

            # whitelist folders
            create_whitelist(save_folder, FOLDERS_TO_CREATE)

            # list containing relative paths to CSS files, for retrieving web resources within these files later on
            css_files = []

            # find all web resources in link tags that are not a stylesheet
            for elm in root.xpath("//link[@rel!='stylesheet' and @type!='text/css' and @href]"):
                if elm.get('href'):
                    # save resource
                    resource_path = save_resource(url, elm.get('href'), save_folder)
                    # set new path to web resource
                    resource_path = add_webfiles_tags_to_resource_path(resource_path)
                    elm.set('href', resource_path)

            # find all external stylesheets
            # xpath expression returns directly the value of href
            for elm in root.xpath("//link[@rel='stylesheet' and @href or @type='text/css' and @href]"):
                if elm.get('href'):
                    href = elm.get('href')
                    # save resource
                    resource_path = save_resource(url, href, save_folder)
                    # store path to css file and url as tuple in list
                    # which will be iterated over later for getting resources within the css files
                    css_files.append((resource_path, href))
                    # set new path to web resource
                    resource_path = add_webfiles_tags_to_resource_path(resource_path)
                    elm.set('href', resource_path)

            # find all web resources from elements with src attribute (<script> and <img> elements)
            # xpath expression returns directly the value of src
            for elm in root.xpath('//*[@src]'):
                if elm.get('src') and not elm.get('src').startswith('data:'):
                    # save resource
                    resource_path = save_resource(url, elm.get('src'), save_folder)
                    # set new path to web resource
                    resource_path = add_webfiles_tags_to_resource_path(resource_path)
                    elm.set('src', resource_path)

            # find all web resources from elements with data-src attribute (HTML5)
            # xpath expression returns directly the value of data-src
            for elm in root.xpath('//*[@data-src]'):
                if elm.get('data-src'):
                    # save resource
                    resource_path = save_resource(url, elm.get('data-src'), save_folder)
                    # set new path to web resource
                    resource_path = add_webfiles_tags_to_resource_path(resource_path)
                    elm.set('data-src', resource_path)

            # find web resources in inline stylesheets
            for elm in root.xpath('//style'):
                new_css = save_resources_from_css(url, elm.text, save_folder, False)
                # set new text for element, with updated URLs
                elm.text = new_css

            # find web resources in inline styles
            # xpath expression returns directly the value of style
            for elm in root.xpath('//*[@style]'):
                new_css = save_resources_from_css(url, elm.get('style'), save_folder, False)
                # set style with new path
                elm.set('style', new_css)

            # find web resources in external stylesheets
            for css_file in css_files:
                (css_file_path, css_url) = css_file
                # need to append save_folder to css file path
                css_file_path = "%s/%s" % (save_folder, css_file_path)
                if os.path.isfile(css_file_path):
                    with open(css_file_path, 'r') as f:
                        css_file_contents = f.read()
                        # get fully qualified URL to css file, regardless if URL is a full URL, relative or absolute
                        css_full_url = urlparse.urljoin(url, css_url)
                        new_css_file_content = save_resources_from_css(css_full_url, css_file_contents, save_folder, True)
                    with open(css_file_path, 'w') as f:
                        f.write(new_css_file_content)
                else:
                    logger.error("Cannot find CSS file for extracting web resources: %s", css_file_path)

            # save ftl/html
            html_file_contents = html.tostring(root)
            if not args.html:
                file_name = "%s/%s" % (save_folder, TEMPLATE_FILE_NAME_FTL)
                # add webfiles import tag for importing tag libraries
                html_file_contents = FTL_IMPORT_TAG + html_file_contents
            else:
                file_name = "%s/%s" % (save_folder, TEMPLATE_FILE_NAME_HTML)

            # replace placeholders for webfiles tags
            html_file_contents = html_file_contents.replace(WEBFILES_START_TAG_SEARCHREPLACE, WEBFILES_START_TAG)
            html_file_contents = html_file_contents.replace(WEBFILES_END_TAG_SEARCHREPLACE, WEBFILES_END_TAG)

            # save to file
            with open(file_name, 'w') as f:
                f.write(html_file_contents)
            print("Downloaded resources from {} successfully to folder '{}'".format(url, save_folder))

    except IOError as e:
        logger.error("Could not fetch HTML for URL: %s", e)


if __name__ == '__main__':
    description = "Downloads HTML for URL and downloads all web resources and rewrites links"
    parser = ArgumentParser(description=description)
    parser.add_argument('url', help="URL to extract web resources for", metavar='URL')
    parser.add_argument('output', help="download resources to folder", metavar='FOLDERNAME')
    parser.add_argument('--file', dest="supplied_html", help='use supplied HTML file instead of downloading from URL')
    parser.add_argument('--loglevel', dest="loglevel", help='change default logging level')
    parser.add_argument('-w', '--html', action='store_true', help='save as HTML instead of Freemarker')
    parser.add_argument('-v', '--videos', action='store_true', help='download videos')

    args = parser.parse_args()

    # set loglevel via commandline
    if args.loglevel == "debug":
        logging.getLogger().setLevel(logging.DEBUG)
    elif args.loglevel == "info":
        logging.getLogger().setLevel(logging.INFO)
    elif args.loglevel is not None:
        logger.warn("Warning: log level not recognized")

    main(args.url, args.output)
