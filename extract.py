from lxml import html
from argparse import ArgumentParser
import os
import re
import urllib2
import urlparse


FOLDERS_TO_CREATE = ['css', 'fonts', 'icons', 'images', 'js', 'other']
HEADER = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_5) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/52.0.2743.116 Safari/537.36"
}


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
def get_url(url):
    try:
        request = urllib2.Request(url, headers=HEADER)
        response = urllib2.urlopen(request)

        return response.read()
    except urllib2.HTTPError, e:
        if e.code == 404:
            print "Error 404, resource not found: %s" % url
        else:
            print "Error with status code %s for URL: %s" % (e.code, url)
    except urllib2.URLError, e:
            print "Error %s for URL: %s" % (e.reason, url)


# returns full URL, regardless of URL having an absolute, relative or full path
def get_download_path(url, base_url, full_url):
    # add scheme, if URL does not contain scheme
    if url.startswith('//'):
        download_path = urlparse.urlparse(base_url).scheme + ':' + url
    # base or full URL only needs to be appended if it is an external resource
    elif '//' in url:
        download_path = url
    # for absolute paths use the base URL
    elif url.startswith('/'):
        download_path = base_url + url
    # for relative paths use the full URL
    else:
        download_path = full_url + url

    return download_path


# download web resource, determine full URL and save location
def save_resource(url, save_folder, base_url, full_url):
    # get filename and extension of resource
    file_name = urlparse.urlsplit(url).path.split('/')[-1]
    ext = file_name.split('.')[-1].lower()

    # determine which folder the resource should be saved to (image, font, etc.)
    folder = select_folder(ext)
    save_path = "%s/%s/%s" % (save_folder, folder, file_name)

    # do not download videos unless flag has been set
    if folder == 'videos' and not args.videos:
        return "NOT_DOWNLOADED/" + url

    # create full URL to download, regardless if URL has an absolute, relative or full path
    download_path = get_download_path(url, base_url, full_url)

    # only download if file is not already existing (has been downloaded before)
    if not os.path.isfile(save_path):
        response = get_url(download_path)
        if response:
            print "Saving external resource with URL '%s' to '%s" % (download_path, save_path)
            with open(save_path, 'w') as f:
                f.write(response)
    else:
        print "File already exists: %s" % save_path

    return save_path


# search CSS stylesheet (string) for web resources and download them
def save_resources_from_css(stylesheet_string, save_folder, base_url, full_url, relpath):
    # check if a style element does not contain text so no exception is raised
    if stylesheet_string:
        # use regexp to search for url(...)
        iter_url = re.finditer(r'url\(([^)]*)\)', stylesheet_string)
        # iterate over result
        for url in iter_url:
            if url.groups():
                # remove leading and trailing ' and "
                if url.group(1).startswith('\'') or url.group(1).startswith('"'):
                    sanitized_url = url.group(1)[1:-1]
                else:
                    sanitized_url = url.group(1)

                # check if URL does not contain binary data, if not save resource
                if sanitized_url and not sanitized_url.startswith('data:'):
                    # save resource
                    save_path = save_resource(sanitized_url, save_folder, base_url, full_url)
                    # modify path, as the web resources are requested from the /css folder
                    # only do this for external stylesheets, not for internal or inline styles
                    if relpath:
                        save_path = save_path(save_folder, '..', 1)
                    # replace url with new path
                    stylesheet_string = stylesheet_string[url.start()+4] + save_path + stylesheet_string[url.end()-1]

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


def get_file_name_for_url(url):
    # write HTML to file
    file_name = url.split('/')[-1]
    # add .html to filename if it does not have it already
    if not file_name.endswith('.htm') and not file_name.endswith('.html'):
        file_name += '.html'

    return file_name


def main(url, output_folder, folders_to_create):
    try:
        # if page has already been downloaded before, use local copy
        file_name = get_file_name_for_url(url)
        if not os.path.isfile(file_name):
            # parse HTML from URL
            root = html.fromstring(get_url(url))
        else:
            # parse HTML from local file
            root = html.parse(file_name)

        if root is not None:
            # prepare folders
            create_folders(output_folder, folders_to_create)

            # get URLs for downloading web resources
            base_url = get_base_url(url)
            full_url = get_full_url(url)

            # dict containing relative paths to CSS files, for retrieving web resources within these files later on
            stylesheets_path = {}

            # find all web resources in link tags that are not a stylesheet
            for elm in root.xpath("//link[@rel!='stylesheet' and @type!='text/css' and @href]"):
                if elm.get('href'):
                    # save resource
                    save_path = save_resource(elm.get('href'), output_folder, base_url, full_url)
                    # set new path to web resource
                    elm.set('href', save_path)

            # find all external stylesheets
            # xpath expression returns directly the value of href
            for elm in root.xpath("//link[@rel='stylesheet' and @type='text/css' and @href]"):
                if elm.get('href'):
                    href = elm.get('href')
                    # save resource
                    save_path = save_resource(href, output_folder, base_url, full_url)
                    # store relative path to CSS files, for retrieving web resources within these files later on
                    if '//' in href:
                        download_path = href
                    else:
                        download_path = get_download_path(href, base_url, full_url)
                    # store relative path in dict with as key the filename of the stylesheet
                    stylesheet_file_name = urlparse.urlsplit(href).path.split('/')[-1]
                    stylesheets_path[stylesheet_file_name] = download_path
                    # set new path to web resource
                    elm.set('href', save_path)

            # find all web resources from elements with src attribute (<script> and <img> elements)
            # xpath expression returns directly the value of src
            for elm in root.xpath('//*[@src]'):
                if elm.get('src'):
                    # save resource
                    save_path = save_resource(elm.get('src'), output_folder, base_url, full_url)
                    # set new path to web resource
                    elm.set('src', save_path)

            # find web resources in inline stylesheets
            for elm in root.xpath('//style'):
                new_css = save_resources_from_css(elm.text, output_folder, base_url, full_url, False)
                # set new text for element, with updated URLs
                elm.text = new_css

            # find web resources in inline styles
            # xpath expression returns directly the value of style
            for elm in root.xpath('//*[@style]'):
                new_css = save_resources_from_css(elm.get('style'), output_folder, base_url, full_url, False)
                # set style with new path
                elm.set('style', new_css)

            # find web resources in external stylesheets
            for css_file in os.listdir(output_folder + '/css'):
                css_file_name = output_folder + '/css/' + css_file
                if os.path.isfile(css_file_name):
                    # get relative path to CSS file for downloading web resources
                    if css_file in stylesheets_path:
                        css_file_path = stylesheets_path[css_file]
                        stylesheet_base_url = get_base_url(css_file_path)
                        stylesheet_full_url = get_full_url(css_file_path)
                        with open(css_file_name, 'r') as f:
                            file_contents = f.read()
                            new_css = save_resources_from_css(file_contents, output_folder, stylesheet_base_url,
                                                              stylesheet_full_url, True)
                        with open(css_file_name, 'w') as f:
                            f.write(new_css)

            # save page if not been downloaded before
            if not os.path.isfile(file_name):
                with open(file_name, 'w') as f:
                    f.write(html.tostring(root))

    except IOError as e:
        print "Could not fetch HTML for URL: %s" % e


if __name__ == '__main__':
    description = "Downloads HTML for URL and downloads all web resources and rewrites links"
    parser = ArgumentParser(description=description)
    parser.add_argument('url', help="URL to extract web resources for", metavar='URL')
    parser.add_argument('output', help="download resources to folder", metavar='FOLDERNAME')
    parser.add_argument('-v', '--videos', action='store_true', help='download videos')

    args = parser.parse_args()
    main(args.url, args.output, FOLDERS_TO_CREATE)
