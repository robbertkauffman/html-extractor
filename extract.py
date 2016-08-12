from lxml import html
from argparse import ArgumentParser
import os
import re
import urllib2
import urlparse


FOLDERS_TO_CREATE = ['css', 'fonts', 'images', 'js', 'other']
HEADER = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_5) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/52.0.2743.116 Safari/537.36"
}


def create_folders(save_folder, folder_list):
    for folder in folder_list:
        folder_path = "%s/%s" % (save_folder, folder)
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)


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


def save_resource(url, save_folder, base_url, full_url):
    # get filename and extension of resource
    file_name = urlparse.urlsplit(url).path.split('/')[-1]
    ext = file_name.split('.')[-1].lower()

    # determine which folder resource should be saved to (image, font, etc.)
    folder = select_folder(ext)
    save_path = "%s/%s/%s" % (save_folder, folder, file_name)


    # add scheme, if URL does not contain scheme
    if url.startswith('//'):
        download_path = urlparse.urlparse(base_url).scheme + ':' + url
    # base or full URL only needs to be appended if it is an external resource
    elif '//' in url:
        download_path = url
    elif url.startswith('/'):
        download_path = base_url + url
    else:
        download_path = full_url + url

    response = get_url(download_path)
    if response:
        print "Saving external resource with URL '%s' to '%s" % (download_path, save_path)
        with open(save_path, 'w') as f:
            f.write(response)

    return save_path


def save_resources_from_css(stylesheet_string, save_folder, base_url, full_url):
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
                if not sanitized_url.startswith('data:'):
                    # save resource
                    save_path = save_resource(sanitized_url, save_folder, base_url, full_url)
                    # replace url with new path
                    stylesheet_string = stylesheet_string.replace(sanitized_url, save_path, url.start())

    return stylesheet_string


def select_folder(ext):
    return {
        'css': 'css',
        'js': 'js',
        # images
        'gif': 'images',
        'jpeg': 'images',
        'jpg': 'images',
        'png': 'images',
        'ico': '',
        # fonts
        'eot': 'fonts',
        'svg': 'fonts',
        'ttf': 'fonts',
        'woff': 'fonts',
        'woff2': 'fonts',
        'other': 'other',
    }.get(ext, 'other')


def main(url, output_folder, folders_to_create):
    try:
        # parse HTML from URL
        root = html.fromstring(get_url(url))
        if root is not None:
            # prepare folders
            create_folders(output_folder, folders_to_create)

            # get URLs for downloading web resources
            # base URL for retrieving resources with absolute path (URL starts with '/')
            # full URL for retrieving resources with relative path
            base_url = url
            if not urlparse.urlparse(url).path:
                full_url = base_url
            else:
                base_url = "/".join(url.split('/')[:3])
                full_url = "/".join(url.split('/')[:-1])

            # append / to full URL and remove trailing / for base URL, for downloading web resources
            if base_url.endswith('/'):
                base_url = base_url[:-1]
            if not full_url.endswith('/'):
                full_url += '/'

            # find all external stylesheets
            # xpath expression returns directly the value of href
            for src in root.xpath('//link/@href'):
                # save resource
                save_path = save_resource(src, output_folder, base_url, full_url)

                # set src to new path
                elm = src.getparent()
                elm.set('href', save_path)

            # find all web resources from elements with src attribute (<script> and <img> elements)
            # xpath expression returns directly the value of src
            for src in root.xpath('//*/@src'):
                # save resource
                save_path = save_resource(src, output_folder, base_url, full_url)

                # set src to new path
                elm = src.getparent()
                elm.set('src', save_path)

            # find web resources in inline stylesheets
            for elm in root.xpath('//style'):
                new_css = save_resources_from_css(elm.text, output_folder, base_url, full_url)
                # set new text for element, with updated URLs
                elm.text = new_css

            # find web resources in inline styles
            # xpath expression returns directly the value of style
            for style in root.xpath('//*/@style'):
                new_css = save_resources_from_css(style, output_folder, base_url, full_url)

                # set style with new path
                elm = style.getparent()
                elm.set('style', new_css)

            # find web resources in external stylesheets
            # TODO: add relative path of css file for retrieving web resources
            for css_file in os.listdir(output_folder + '/css'):
                css_file_name = output_folder + '/css/' + css_file
                if os.path.isfile(css_file_name):
                    with open(css_file_name, 'r') as f:
                        file_contents = f.read()
                        new_css = save_resources_from_css(file_contents, output_folder, base_url, full_url)
                    with open(css_file_name, 'w') as f:
                        f.write(new_css)

            # write HTML to file
            file_name = url.split('/')[-1]
            # add .html to filename if it does not have it already
            if not file_name.endswith('.htm') and not file_name.endswith('.html'):
                file_name += '.html'
            with open(file_name, 'w') as f:
                f.write(html.tostring(root))

    except IOError as e:
        print "Could not fetch HTML for URL: %s" % e


if __name__ == '__main__':
    description = "Downloads HTML for URL and downloads all web resources and rewrites links"
    parser = ArgumentParser(description=description)
    parser.add_argument("url", help="URL to extract web resources for", metavar="URL")
    parser.add_argument("output", help="download resources to folder", metavar="FOLDERNAME")

    args = parser.parse_args()
    main(args.url, args.output, FOLDERS_TO_CREATE)
