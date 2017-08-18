from lxml import html
from argparse import ArgumentParser
import logging
import os
import re
import urllib2
import urlparse


FOLDERS_TO_CREATE = ['css', 'fonts', 'icons', 'images', 'js', 'other']
HEADER = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_5) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/60.0.3112.90 Safari/537.36"
}
TEMPLATE_FILE_NAME = "base-layout.html"
WEBFILES_START_TAG = "<@hst.webfile  path=\""
WEBFILES_END_TAG = "\"/>"

# initiate logger
logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


# create folders for storing all web resources, categorized by type (CSS, fonts, etc.)
def create_folders(save_folder, folder_list):
    for folder in folder_list:
        folder_path = "%s/%s" % (save_folder, folder)
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)


# get URLs for downloading web resources
# base URL for retrieving resources with absolute path (URL starts with '/')
def get_base_url(url):
    if not urlparse.urlparse(url).path:
        base_url = url
    else:
        base_url = "/".join(url.split('/')[:3])

    # remove trailing / for base URL for downloading web resources
    if base_url.endswith('/'):
        base_url = base_url[:-1]

    return base_url


# get URLs for downloading web resources
# full URL for retrieving resources with relative path
def get_full_url(url):
    if not urlparse.urlparse(url).path:
        full_url = url
    else:
        full_url = "/".join(url.split('/')[:-1])

    # append / to full URL for downloading web resources
    if not full_url.endswith('/'):
        full_url += '/'

    return full_url


# download resource for URL, raise error if 404 or other error is returned
def download_resource(origin_url, url):
    # get fully qualified URL, regardless if URL is a full URL, relative or absolute
    url = urlparse.urljoin(origin_url, url)

    # download resource
    try:
        request = urllib2.Request(url, headers=HEADER)
        response = urllib2.urlopen(request)

        return response.read()
    except urllib2.HTTPError, e:
        if e.code == 404:
            logger.error("Error 404, resource not found: %s", url)
        else:
            logger.error("Error with status code %s for URL: %s", e.code, url)
    except urllib2.URLError, e:
            logger.error("Error %s for URL: %s", e.reason, url)


# download web resource, determine full URL and save location
def save_resource(origin_url, url, save_folder):
    # get filename and extension of resource
    file_name = urlparse.urlsplit(url).path.replace('/', '-').lstrip('-')
    ext = file_name.split('.')[-1].lower()

    # determine which folder the resource should be saved to (image, font, etc.)
    folder = select_folder(ext)
    resource_path = "%s/%s" % (folder, file_name)

    # do not download videos unless flag has been set
    if folder == 'videos' and not args.videos:
        return url

    # add save_folder to resource path to determine path for saving the resource
    save_path = "%s/%s" % (save_folder, resource_path)

    # only download if file is not already existing (has been downloaded before)
    if not os.path.isfile(save_path):
        response = download_resource(origin_url, url)
        if response:
            logger.info("Saving external resource with URL '%s' to '%s", url, save_path)
            with open(save_path, 'w') as f:
                f.write(response)
        else:
            return url
    else:
        logger.warn("File already exists: %s", save_path)

    # encapsulate the path to the web resource in the webfile tag,
    # so the link works directly in Hippo
    # resource_path = WEBFILES_START_TAG + resource_path + WEBFILES_END_TAG

    return resource_path


# search CSS stylesheet (string) for web resources and download them
def save_resources_from_css(origin_url, stylesheet_string, save_folder):
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
                save_path = save_resource(origin_url, sanitized_url, save_folder)
                # modify path, as the web resources are requested from the /css folder
                # only do this for external stylesheets, not for internal or inline styles
                # if relpath:
                #     save_path = save_path.replace(save_folder, '..', 1)
                # replace url with new path
                stylesheet_string = stylesheet_string[:url.start(1)] + save_path + stylesheet_string[url.end(1):]
                # update position for next search
                pos = url.start(1) + len(save_path) + 1
            else:
                # update position for next search
                pos = url.end(0)

            # do new search
            url = pattern.search(stylesheet_string, pos)

    return stylesheet_string


# switch-case statement used by create_folders()
def select_folder(ext):
    return {
        'css': 'css',
        'js': 'js',
        # images
        'gif': 'images',
        'jpeg': 'images',
        'jpg': 'images',
        'png': 'images',
        # icons
        'ico': 'icons',
        # fonts
        'eot': 'fonts',
        'svg': 'fonts',
        'ttf': 'fonts',
        'woff': 'fonts',
        'woff2': 'fonts',
        'other': 'other',
        # videos
        'mp4': 'videos',
        'ogv': 'videos',
        'webm': 'videos',
        'mov': 'videos'
    }.get(ext, 'other')


def main(url, output_folder):
    try:
        # download resource from URL and parse HTML
        root = html.fromstring(download_resource(url, ""))

        if root is not None:
            # prepare folders
            create_folders(output_folder, FOLDERS_TO_CREATE)

            # list containing relative paths to CSS files, for retrieving web resources within these files later on
            css_files = []

            # find all web resources in link tags that are not a stylesheet
            for elm in root.xpath("//link[@rel!='stylesheet' and @type!='text/css' and @href]"):
                if elm.get('href'):
                    # save resource
                    resource_path = save_resource(url, elm.get('href'), output_folder)
                    # set new path to web resource
                    elm.set('href', resource_path)

            # find all external stylesheets
            # xpath expression returns directly the value of href
            for elm in root.xpath("//link[@rel='stylesheet' and @href or @type='text/css' and @href]"):
                if elm.get('href'):
                    href = elm.get('href')
                    # save resource
                    resource_path = save_resource(url, href, output_folder)
                    # store path to css file and url as tuple in list
                    # which will be iterated over later for getting resources within the css files
                    css_files.append((resource_path, href))
                    # set new path to web resource
                    elm.set('href', resource_path)

            # find all web resources from elements with src attribute (<script> and <img> elements)
            # xpath expression returns directly the value of src
            for elm in root.xpath('//*[@src]'):
                if elm.get('src'):
                    # save resource
                    resource_path = save_resource(url, elm.get('src'), output_folder)
                    # set new path to web resource
                    elm.set('src', resource_path)

            # find all web resources from elements with data-src attribute (HTML5)
            # xpath expression returns directly the value of data-src
            for elm in root.xpath('//*[@data-src]'):
                if elm.get('data-src'):
                    # save resource
                    resource_path = save_resource(url, elm.get('data-src'), output_folder)
                    # set new path to web resource
                    elm.set('data-src', resource_path)

            # find web resources in inline stylesheets
            for elm in root.xpath('//style'):
                new_css = save_resources_from_css(url, elm.text, output_folder)
                # set new text for element, with updated URLs
                elm.text = new_css

            # find web resources in inline styles
            # xpath expression returns directly the value of style
            for elm in root.xpath('//*[@style]'):
                new_css = save_resources_from_css(url, elm.get('style'), output_folder)
                # set style with new path
                elm.set('style', new_css)

            # find web resources in external stylesheets
            for css_file in css_files:
                (css_file_path, css_url) = css_file
                # need to append output_folder to css file path
                css_file_path = "%s/%s" % (output_folder, css_file_path)
                if os.path.isfile(css_file_path):
                    with open(css_file_path, 'r') as f:
                        css_file_contents = f.read()
                        new_css_file_content = save_resources_from_css(css_url, css_file_contents, output_folder)
                    with open(css_file_path, 'w') as f:
                        f.write(new_css_file_content)

            # save page
            file_name = "%s/%s" % (output_folder, TEMPLATE_FILE_NAME)
            with open(file_name, 'w') as f:
                f.write(html.tostring(root))

    except IOError as e:
        logger.error("Could not fetch HTML for URL: %s", e)


if __name__ == '__main__':
    description = "Downloads HTML for URL and downloads all web resources and rewrites links"
    parser = ArgumentParser(description=description)
    parser.add_argument('url', help="URL to extract web resources for", metavar='URL')
    parser.add_argument('output', help="download resources to folder", metavar='FOLDERNAME')
    parser.add_argument('-v', '--videos', action='store_true', help='download videos')

    args = parser.parse_args()
    main(args.url, args.output)
