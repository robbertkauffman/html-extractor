# Hippo HTML Extractor

The Hippo HTML Extractor script extracts HTML of a given site for use in Hippo CMS. Saving 
the HTML with your browser doesn't extract any fonts, images referenced in the CSS files. 
This script saves all referenced resources in HTML and CSS.  

***Note**: this script does not save or rewrite resources referenced in JavaScript files.*

Additionally, it can save the HTML as FTL (Freemarker) and automatically put links to 
resources in the <@hst.webfile/> tags. You can simply copy the Freemarker file and the 
resource folders to Experience, and you should be good to go.

## Requirements
To run the script you need Python 2.7.9 or higher. [Download Python 2.7.x here](https://www.python.org/downloads/release/python-2713/)

You also need the [lxml library](http://lxml.de/installation.html) and the 
[requests library](http://docs.python-requests.org/en/master/user/install/#install). You can install these 
via the command line when you have Python >= 2.79 installed:
```bash
    $ pip install lxml
    $ pip install requests
```

## Usage
Run the following command in the folder that contains the `extract.py` script.
```bash
    $ python extract.py URL OUTPUT_FOLDER
```

This downloads the HTML from the specified URL and downloads any resources referenced in 
the HTML and CSS. After this, you can copy all the subfolders to your project's webfiles 
folder (on Mac/Linux):
* v12: `cp -R OUTPUT_FOLDER PATH_TO_PROJECT/repository-data/webfiles/src/main/resources/site`
* v11: `cp -R OUTPUT_FOLDER PATH_TO_PROJECT/bootstrap/webfiles/src/main/resources/site`

Move base-layout.ftl to the correct directory, overwriting the existing file in your project:
* v12: `mv PATH_TO_PROJECT/repository-data/webfiles/src/main/resources/site/base-layout.ftl PATH_TO_PROJECT/repository-data/webfiles/src/main/resources/site/freemarker/PROJECTNAME (e.g. myhippoproject)`
* v11: `mv PATH_TO_PROJECT/bootstrap/webfiles/src/main/resources/site/base-layout.ftl PATH_TO_PROJECT/bootstrap/webfiles/src/main/resources/site/freemarker/PROJECTNAME (e.g. myhippoproject)`

The site should now look very similar if not exactly like the site that you have extracted.
For demos, you will still need to break down the template in sub templates (header, main, 
footer, etc.) and do the same for components.

## Troubleshooting
If some resources fail to load after importing to your project, you may need to adjust the configuration of `/hippo:configuration/hippo:modules/webfiles/hippo:moduleconfig`.  This module configuration specifies allowable file types and max file size for webfiles.  Upon completion, `extract.py` will print information about the maximum file size and a list of file types.  
```
Maximum file size: 985 KB
File types: ['*.ico', '*.css', '*.png', '*.jpg', '*.js', '*.otf', '*.ttf']
```
Use this information to configure the webfiles module.  Alternatively, consider packaging large files as static resources in the Site WAR.  See: https://www.onehippo.org/library/concepts/web-application/static-webapp-resources.html

## Other
Show help with all available options:
```bash
    $ python extract.py -h
```
