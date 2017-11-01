#!/usr/bin/env python

import logging
import os
import re

from ansibullbot.parsers.botmetadata import BotMetadataParser
from ansibullbot.utils.git_tools import GitRepoWrapper
from ansibullbot.utils.systemtools import run_command


class ComponentMatcher(object):

    BOTMETA = {}
    INDEX = {}
    REPO = 'https://github.com/ansible/ansible'
    STOPWORDS = ['ansible', 'core', 'plugin']
    STOPCHARS = ['"', "'", '(', ')', '?', '*', '`', ',', ':', '?', '-']
    BLACKLIST = ['new module', 'new modules']
    FILE_NAMES = []
    MODULES = {}
    MODULE_NAMES = []
    MODULE_NAMESPACE_DIRECTORIES = []

    # FIXME: THESE NEED TO GO INTO BOTMETA
    # ALSO SEE search_by_regex_generic ...
    KEYWORDS = {
        'all': None,
        'ansiballz': 'lib/ansible/executor/module_common.py',
        'ansible-console': 'lib/ansible/cli/console.py',
        'ansible-galaxy': 'lib/ansible/galaxy',
        'ansible-inventory': 'lib/ansible/cli/inventory.py',
        'ansible-playbook': 'lib/ansible/playbook',
        'ansible playbook': 'lib/ansible/playbook',
        'ansible playbooks': 'lib/ansible/playbook',
        'ansible-pull': 'lib/ansible/cli/pull.py',
        'ansible-vault': 'lib/ansible/parsing/vault',
        'ansible-vault edit': 'lib/ansible/parsing/vault',
        'ansible-vault show': 'lib/ansible/parsing/vault',
        'ansible-vault decrypt': 'lib/ansible/parsing/vault',
        'ansible-vault encrypt': 'lib/ansible/parsing/vault',
        'become': 'lib/ansible/playbook/become.py',
        'block': 'lib/ansible/playbook/block.py',
        'blocks': 'lib/ansible/playbook/block.py',
        'callback plugin': 'lib/ansible/plugins/callback',
        'callback plugins': 'lib/ansible/plugins/callback',
        'conditional': 'lib/ansible/playbook/conditional.py',
        'delegate_to': 'lib/ansible/playbook/task.py',
        'facts': 'lib/ansible/module_utils/facts',
        'galaxy': 'lib/ansible/galaxy',
        'groupvars': 'lib/ansible/vars/hostvars.py',
        'group vars': 'lib/ansible/vars/hostvars.py',
        'handlers': 'lib/ansible/playbook/handler.py',
        'hostvars': 'lib/ansible/vars/hostvars.py',
        'host vars': 'lib/ansible/vars/hostvars.py',
        'integration tests': 'test/integration',
        'inventory script': 'contrib/inventory',
        'jinja2 template system': 'lib/ansible/template',
        'module_utils': 'lib/ansible/module_utils',
        'multiple modules': None,
        'new module(s) request': None,
        'new modules request': None,
        'new module request': None,
        'new module': None,
        'network_cli': 'lib/ansible/plugins/connection/network_cli.py',
        'network_cli.py': 'lib/ansible/plugins/connection/network_cli.py',
        'network modules': 'lib/ansible/modules/network',
        #'playbook role': 'lib/ansible/playbook/role',
        #'playbook roles': 'lib/ansible/playbook/role',
        'paramiko': 'lib/ansible/plugins/connection/paramiko_ssh.py',
        'role': 'lib/ansible/playbook/role',
        'roles': 'lib/ansible/playbook/role',
        'ssh': 'lib/ansible/plugins/connection/ssh.py',
        'ssh authentication': 'lib/ansible/plugins/connection/ssh.py',
        'setup / facts': 'lib/ansible/modules/system/setup.py',
        'setup': 'lib/ansible/modules/system/setup.py',
        'task executor': 'lib/ansible/executor/task_executor.py',
        'testing': 'test/',
        'validate-modules': 'test/sanity/validate-modules',
        'vault': 'lib/ansible/parsing/vault',
        'vault edit': 'lib/ansible/parsing/vault',
        'vault documentation': 'lib/ansible/parsing/vault',
        'with_items': 'lib/ansible/playbook/loop_control.py',
        'windows modules': 'lib/ansible/modules/windows',
        'winrm': 'lib/ansible/plugins/connection/winrm.py'
    }

    def __init__(self, gitrepo=None, botmetafile=None, cachedir=None, file_indexer=None, module_indexer=None):
        self.cachedir = cachedir
        self.botmetafile = botmetafile

        '''
        self.file_indexer = file_indexer
        self.FILE_NAMES = sorted(self.file_indexer.files)
        self.module_indexer = module_indexer
        self.MODULE_NAMES = [x['name'] for x in self.module_indexer.modules.values()]

        self.MODULE_NAMESPACE_DIRECTORIES = [os.path.dirname(x) for x in self.FILE_NAMES if x.startswith('lib/ansible/modules/')]
        self.MODULE_NAMESPACE_DIRECTORIES = sorted(set(self.MODULE_NAMESPACE_DIRECTORIES))
        '''

        if gitrepo:
            self.gitrepo = gitrepo
        else:
            self.gitrepo = GitRepoWrapper(cachedir=self.cachedir, repo=self.REPO)
            self.gitrepo.update()

        self.index_files()

        self.cache_keywords()
        self.strategy = None
        self.strategies = []

    def index_files(self):


        for fn in self.gitrepo.module_files:
            mname = os.path.basename(fn)
            mname = mname.replace('.py', '').replace('.ps1', '')
            if mname.startswith('__'):
                continue
            mdata = {
                'name': mname,
                'repo_filename': fn,
                'filename': fn
            }
            self.MODULES[fn] = mdata.copy()

        self.MODULE_NAMESPACE_DIRECTORIES = [os.path.dirname(x) for x in self.gitrepo.module_files]
        self.MODULE_NAMESPACE_DIRECTORIES = sorted(set(self.MODULE_NAMESPACE_DIRECTORIES))

        # make a list of names by enumerating the files
        self.MODULE_NAMES = [os.path.basename(x) for x in self.gitrepo.module_files]
        self.MODULE_NAMES = [x for x in self.MODULE_NAMES if x.endswith('.py') or x.endswith('.ps1')]
        self.MODULE_NAMES = [x.replace('.ps1', '').replace('.py', '') for x in self.MODULE_NAMES]
        self.MODULE_NAMES = [x for x in self.MODULE_NAMES if not x.startswith('__')]
        self.MODULE_NAMES = sorted(set(self.MODULE_NAMES))

        # make a list of names by calling ansible-doc
        cmd = 'source {}/hacking/env-setup; ansible-doc -t module -l'.format(self.gitrepo.checkoutdir)
        logging.debug(cmd)
        (rc, so, se) = run_command(cmd)
        mnames = so.split('\n')
        mnames = [x.strip() for x in mnames if x.strip()]
        mnames = [x.split()[0] for x in mnames]
        self.MODULE_NAMES += mnames
        self.MODULE_NAMES = sorted(set(self.MODULE_NAMES))


        for mname in self.MODULE_NAMES:
            matched = False
            for k,v in self.MODULES.items():
                if v['name'] == mname:
                    matched = True
                    break
            if not matched:
                fn = 'lib/ansible/modules/None/{}'.format(mname)
                mdata = {
                    'name': mname,
                    'repo_filename': fn,
                    'filename': fn
                }
                self.MODULES[fn] = mdata.copy()

        # ansible-doc: error: option -t: invalid choice: u'None' (choose from
        # 'cache', 'callback', 'connection', 'inventory', 'lookup', 'module',
        # 'strategy', 'vars')
        #import epdb; epdb.st()

        self.load_meta()

    def load_meta(self):
        if self.botmetafile is not None:
            with open(self.botmetafile, 'rb') as f:
                rdata = f.read()
        else:
            fp = '.github/BOTMETA.yml'
            rdata = self.gitrepo.get_file_content(fp)
        self.BOTMETA = BotMetadataParser.parse_yaml(rdata)
        #import epdb; epdb.st()

    def cache_keywords(self):
        for k,v in self.BOTMETA['files'].items():
            if not v.get('keywords'):
                continue
            for kw in v['keywords']:
                if kw not in self.KEYWORDS:
                    self.KEYWORDS[kw] = k

    def _cache_keywords(self):
        """Make a map of keywords and module names"""
        for k,v in self.file_indexer.botmeta['files'].items():
            if not v.get('keywords'):
                continue
            for kw in v['keywords']:
                if kw not in self.KEYWORDS:
                    self.KEYWORDS[kw] = k

        for k,v in self.module_indexer.modules.items():
            if not v.get('name'):
                continue
            if v['name'] not in self.KEYWORDS:
                self.KEYWORDS[v['name']] = v['repo_filename']
            if v['name'].startswith('_'):
                vname = v['name'].replace('_', '', 1)
                if vname not in self.KEYWORDS:
                    self.KEYWORDS[vname] = v['repo_filename']

        for k,v in self.file_indexer.CMAP.items():
            if k not in self.KEYWORDS:
                self.KEYWORDS[k] = v

        for kw in self.BLACKLIST:
            self.KEYWORDS[kw] = None

    def clean_body(self, body, internal=False):
        body = body.lower()
        body = body.strip()
        for SC in self.STOPCHARS:
            if body.startswith(SC):
                body = body.lstrip(SC)
                body = body.strip()
            if body.endswith(SC):
                body = body.rstrip(SC)
                body = body.strip()
            if internal and SC in body:
                body = body.replace(SC, '')
                body = body.strip()
        body = body.strip()
        return body

    def match_components(self, title, body, component):
        """Make a list of matching files with metadata"""

        self.strategy = None
        self.strategies = []

        component = component.encode('ascii', 'ignore')
        logging.debug('match "{}"'.format(component))

        matched_filenames = []

        #delimiters = ['\n', ',', ' + ', ' & ', ': ']
        delimiters = ['\n', ',', ' + ', ' & ']
        delimited = False
        for delimiter in delimiters:
            if delimiter in component:
                delimited = True
                components = component.split(delimiter)
                for _component in components:
                    _matches = self._match_component(title, body, _component)
                    self.strategies.append(self.strategy)

                    # bypass for blacklist
                    if None in _matches:
                        _matches = []

                    matched_filenames += _matches

                # do not process any more delimiters
                break

        if not delimited:
            matched_filenames += self._match_component(title, body, component)
            self.strategies.append(self.strategy)

            # bypass for blacklist
            if None in matched_filenames:
                return []

        # reduce subpaths
        if matched_filenames:
            matched_filenames = self.reduce_filepaths(matched_filenames)

        '''
        # bypass for blacklist
        if None in matched_filenames:
            return []
        '''

        component_matches = []
        matched_filenames = sorted(set(matched_filenames))
        for fn in matched_filenames:
            component_matches.append(self.get_meta_for_file(fn))

        return component_matches

    def _match_component(self, title, body, component):
        """Find matches for a single line"""
        matched_filenames = []

        # context sets the path prefix to narrow the search window
        if 'module_util' in title.lower() or 'module_util' in component.lower():
            context = 'lib/ansible/module_utils'
        elif 'module util' in title.lower() or 'module util' in component.lower():
            context = 'lib/ansible/module_utils'
        elif 'module' in title.lower() or 'module' in component.lower():
            context = 'lib/ansible/modules'
        elif 'dynamic inventory' in title.lower() or 'dynamic inventory' in component.lower():
            context = 'contrib/inventory'
        elif 'inventory script' in title.lower() or 'inventory script' in component.lower():
            context = 'contrib/inventory'
        elif 'inventory plugin' in title.lower() or 'inventory plugin' in component.lower():
            context = 'lib/ansible/plugins/inventory'
        else:
            context = None

        #component = component.strip()
        #for SC in self.STOPCHARS:
        #    if component.startswith(SC):
        #        component = component.lstrip(SC)
        #        component = component.strip()
        #    if component.endswith(SC):
        #        component = component.rstrip(SC)
        #        component = component.strip()

        #component = self.clean_body(component)

        if not component:
            return []

        if component not in self.STOPWORDS and component not in self.STOPCHARS:

            if not matched_filenames:
                matched_filenames += self.search_by_keywords(component, exact=True)
                if matched_filenames:
                    self.strategy = 'search_by_keywords'

            if not matched_filenames:
                matched_filenames += self.search_by_module_name(component)
                if matched_filenames:
                    self.strategy = 'search_by_module_name'

            if not matched_filenames:
                matched_filenames += self.search_by_regex_module_globs(component)
                if matched_filenames:
                    self.strategy = 'search_by_regex_module_globs'

            if not matched_filenames:
                matched_filenames += self.search_by_regex_modules(component)
                if matched_filenames:
                    self.strategy = 'search_by_regex_modules'

            if not matched_filenames:
                matched_filenames += self.search_by_regex_generic(component)
                if matched_filenames:
                    self.strategy = 'search_by_regex_generic'

            if not matched_filenames:
                matched_filenames += self.search_by_regex_urls(component)
                if matched_filenames:
                    self.strategy = 'search_by_regex_urls'

            if not matched_filenames:
                matched_filenames += self.search_by_tracebacks(component)
                if matched_filenames:
                    self.strategy = 'search_by_tracebacks'

            if not matched_filenames:
                matched_filenames += self.search_by_filepath(component, context=context)
                if matched_filenames:
                    self.strategy = 'search_by_filepath'
                if not matched_filenames:
                    matched_filenames += self.search_by_filepath(component, partial=True)
                    if matched_filenames:
                        self.strategy = 'search_by_filepath[partial]'

            if not matched_filenames:
                matched_filenames += self.search_by_keywords(component, exact=False)
                if matched_filenames:
                    self.strategy = 'search_by_keywords!exact'

            if matched_filenames:
                matched_filenames += self.include_modules_from_test_targets(matched_filenames)

        return matched_filenames

    '''
    def search_by_fileindexer(self, title, body, component):
        """Use the fileindexers component matching algo"""
        matches = []
        template_data = {'component name': component, 'component_raw': component}
        ckeys = self.file_indexer.find_component_match(title, body, template_data)
        if ckeys:
            components = self.file_indexer.find_component_matches_by_file(ckeys)
            import epdb; epdb.st()
        return matches
    '''

    def search_by_module_name(self, component):
        matches = []

        #_component = component

        #for SC in self.STOPCHARS:
        #    component = component.replace(SC, '')
        #component = component.strip()
        component = self.clean_body(component)

        # docker-container vs. docker_container
        if component not in self.MODULE_NAMES:
            component = component.replace('-', '_')

        if component in self.MODULE_NAMES:
            #mmatch = self.module_indexer.find_match(component, exact=True)
            mmatch = self.find_module_match(component)
            if mmatch:
                if isinstance(mmatch, list):
                    for x in mmatch:
                        matches.append(x['repo_filename'])
                else:
                    matches.append(mmatch['repo_filename'])

        return matches

    def search_by_keywords(self, component, exact=True):
        """Simple keyword search"""

        component = component.lower()
        matches = []
        if component in self.STOPWORDS:
            matches = [None]
        elif component in self.KEYWORDS:
            matches = [self.KEYWORDS[component]]
        elif not exact:
            for k,v in self.KEYWORDS.items():
                if ' ' + k + ' ' in component or ' ' + k + ' ' in component.lower():
                    logging.debug('keyword match: {}'.format(k))
                    matches.append(v)
                elif ' ' + k + ':' in component or ' ' + k + ':' in component:
                    logging.debug('keyword match: {}'.format(k))
                    matches.append(v)
                elif component.endswith(' ' + k) or component.lower().endswith(' ' + k):
                    logging.debug('keyword match: {}'.format(k))
                    matches.append(v)

                #elif k + ' module' in component:
                #    logging.debug('keyword match: {}'.format(k))
                #    matches.append(v)

                elif (k in component or k in component.lower()) and k in self.BLACKLIST:
                    logging.debug('blacklist  match: {}'.format(k))
                    matches.append(None)

        return matches

    def search_by_regex_urls(self, body):
        # http://docs.ansible.com/ansible/latest/copy_module.html
        # http://docs.ansible.com/ansible/latest/dev_guide/developing_modules.html
        # http://docs.ansible.com/ansible/latest/postgresql_db_module.html
        # [helm module](https//docs.ansible.com/ansible/2.4/helm_module.html)
        # Windows module: win_robocopy\nhttp://docs.ansible.com/ansible/latest/win_robocopy_module.html
        # Examples:\n* archive (https://docs.ansible.com/ansible/archive_module.html)\n* s3_sync (https://docs.ansible.com/ansible/s3_sync_module.html)
        # https//github.com/ansible/ansible/blob/devel/lib/ansible/modules/windows/win_dsc.ps1L228

        matches = []

        urls = re.findall(
            'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+',
            body
        )
        if urls:
            for url in urls:
                url = url.rstrip(')')
                if '/blob' in url and url.endswith('.py'):
                    parts = url.split('/')
                    bindex = parts.index('blob')
                    fn = '/'.join(parts[bindex+2:])
                    matches.append(fn)
                elif '_module.html' in url:
                    parts = url.split('/')
                    fn = parts[-1].replace('_module.html', '')
                    choices = [x for x in self.gitrepo.files if '/' + fn in x or '/_' + fn in x]
                    choices = [x for x in choices if 'lib/ansible/modules' in x]

                    if len(choices) > 1:
                        #choices = [x for x in choices if fn + '.py' in x or fn + '.ps1' in x]
                        choices = [x for x in choices if '/' + fn + '.py' in x or '/' + fn + '.ps1' in x or '/_' + fn + '.py' in x]

                    if not choices:
                        pass
                    elif len(choices) == 1:
                        matches.append(choices[0])
                    else:
                        #import epdb; epdb.st()
                        pass
                else:
                    pass

        #if 's3_module' in body and not matches:
        #    import epdb; epdb.st()

        return matches

    def search_by_regex_modules(self, body):
        # foo module
        # foo and bar modules
        # foo* modules
        # foo* module

        body = body.lower()
        logging.debug('regex match on: {}'.format(body))

        # https://www.tutorialspoint.com/python/python_reg_expressions.htm
        patterns = [
            r'\:\n(\S+)\.py',
            r'(\S+)\.py',
            r'\-(\s+)(\S+)(\s+)module',
            r'\`ansible_module_(\S+)\.py\`',
            r'module(\s+)\-(\s+)(\S+)',
            r'module(\s+)(\S+)',
            r'\`(\S+)\`(\s+)module',
            r'(\S+)(\s+)module',
            r'the (\S+) command',
            r'(\S+) \(.*\)',
            r'(\S+)\-module',
            r'modules/(\S+)',
            r'module\:(\s+)\`(\S+)\`',
            r'module\: (\S+)',
            r'module (\S+)',
            r'module `(\S+)`',
            r'module: (\S+)',
            #r'Module (\S+)',
            #r'Module: (\S+)',
            r'new (\S+) module',
            r'the (\S+) module',
            r'the \"(\S+)\" module',
            r':\n(\S+) module',
            r'(\S+) module',
            r'(\S+) core module',
            r'(\S+) extras module',
            r':\n\`(\S+)\` module',
            r'\`(\S+)\` module',
            r'`(\S+)` module',
            r'(\S+)\* modules',
            r'(\S+) and (\S+)',
            r'(\S+) or (\S+)',
            r'(\S+) \+ (\S+)',
            r'(\S+) \& (\S)',
            r'(\S+) and (\S+) modules',
            r'(\S+) or (\S+) module',
            r'(\S+)_module',
            r'action: (\S+)',
            r'action (\S+)',
            r'ansible_module_(\S+)\.py',
            r'ansible_module_(\S+)',
            r'ansible_modules_(\S+)\.py',
            r'ansible_modules_(\S+)',
            r'(\S+) task',
            r'(\s+)\((\S+)\)',
            #r'(.*)(\s+)\((\S+)\)',
            #r'(\S+) (\S+)',
            #r'(\S+) .*',
            r'(\S+)(\s+)(\S+)(\s+)modules',
            r'(\S+)(\s+)module\:(\s+)(\S+)',
            r'\-(\s+)(\S+)(\s+)module',
            r'\:(\s+)(\S+)(\s+)module',
            r'\-(\s+)ansible(\s+)(\S+)(\s+)(\S+)(\s+)module',
            r'.*(\s+)(\S+)(\s+)module.*'
        ]

        matches = []

        logging.debug('check patterns against: {}'.format(body))

        for pattern in patterns:
            #logging.debug('test pattern: {}'.format(pattern))

            mobj = re.match(pattern, body, re.M | re.I)

            #if not mobj:
            #    logging.debug('pattern {} !matched on "{}"'.format(pattern, body))

            if mobj:
                logging.debug('pattern {} matched on "{}"'.format(pattern, body))

                for x in range(0,mobj.lastindex+1):
                    try:
                        mname = mobj.group(x)
                        if mname == body:
                            continue
                        mname = self.clean_body(mname)
                        if not mname.strip():
                            continue
                        mname = mname.strip().lower()
                        if ' ' in mname:
                            continue
                        mname = mname.replace('.py', '').replace('.ps1', '')
                        logging.debug('--> {}'.format(mname))

                        # attempt to match a module
                        module = None
                        module = self.find_module_match(mname)

                        if not module:
                            pass
                        elif isinstance(module, list):
                            for m in module:
                                #logging.debug('matched {}'.format(m['name']))
                                matches.append(m['repo_filename'])
                        elif isinstance(module, dict):
                            #logging.debug('matched {}'.format(module['name']))
                            matches.append(module['repo_filename'])
                    except Exception as e:
                        logging.error(e)

                if matches:
                    break

        return matches

    def search_by_regex_module_globs(self, body):
        # All AWS modules
        # BigIP modules
        # NXOS modules
        # azurerm modules

        matches = []
        body = self.clean_body(body)
        logging.debug('try globs on: {}'.format(body))

        keymap = {
            'all': None,
            'ec2': 'lib/ansible/modules/cloud/amazon',
            'ec2_*': 'lib/ansible/modules/cloud/amazon',
            'aws': 'lib/ansible/modules/cloud/amazon',
            'amazon': 'lib/ansible/modules/cloud/amazon',
            'google': 'lib/ansible/modules/cloud/google',
            'gce': 'lib/ansible/modules/cloud/google',
            'gcp': 'lib/ansible/modules/cloud/google',
            'bigip': 'lib/ansible/modules/network/f5',
            'nxos': 'lib/ansible/modules/network/nxos',
            'azure': 'lib/ansible/modules/cloud/azure',
            'azurerm': 'lib/ansible/modules/cloud/azure',
            'openstack': 'lib/ansible/modules/cloud/openstack',
            'ios': 'lib/ansible/modules/network/ios',
        }

        regexes = [
            r'(\S+) ansible modules',
            r'all (\S+) based modules',
            r'all (\S+) modules',
            r'.* all (\S+) modules.*',
            r'(\S+) modules',
            r'(\S+\*) modules',
            r'all cisco (\S+\*) modules',
        ]

        mobj = None
        for x in regexes:
            mobj = re.match(x, body)
            if mobj:
                logging.debug('matched glob: {}'.format(x))
                break

        if not mobj:
            logging.debug('no glob matches')

        if mobj:
            keyword = mobj.group(1)
            if not keyword.strip():
                pass
            elif keyword in keymap:
                if keymap[keyword]:
                    matches.append(keymap[keyword])
            else:

                if '*' in keyword:
                    #print(keyword)
                    keyword = keyword.replace('*', '')
                    #import epdb; epdb.st()

                # check for directories first
                fns = [x for x in self.MODULE_NAMESPACE_DIRECTORIES if keyword in x]

                # check for files second
                if not fns:
                    fns = [x for x in self.gitrepo.module_files if 'lib/ansible/modules' in x and keyword in x]

                if fns:
                    matches += fns

        #if body.lower() == 'elasticache modules':
        #    import epdb; epdb.st()

        if matches:
            matches = sorted(set(matches))

        return matches

    def search_by_regex_generic(self, body):
        # foo dynamic inventory script
        # foo filter

        # https://www.tutorialspoint.com/python/python_reg_expressions.htm
        patterns = [
            [r'(.*) action plugin', 'lib/ansible/plugins/action'],
            [r'(.*) inventory plugin', 'lib/ansible/plugins/inventory'],
            [r'(.*) dynamic inventory', 'contrib/inventory'],
            [r'(.*) dynamic inventory (script|file)', 'contrib/inventory'],
            [r'(.*) inventory script', 'contrib/inventory'],
            [r'(.*) filter', 'lib/ansible/plugins/filter'],
            [r'(.*) jinja filter', 'lib/ansible/plugins/filter'],
            [r'(.*) jinja2 filter', 'lib/ansible/plugins/filter'],
            [r'(.*) template filter', 'lib/ansible/plugins/filter'],
            [r'(.*) fact caching plugin', 'lib/ansible/plugins/cache'],
            [r'(.*) fact caching module', 'lib/ansible/plugins/cache'],
            [r'(.*) lookup plugin', 'lib/ansible/plugins/lookup'],
            [r'(.*) lookup', 'lib/ansible/plugins/lookup'],
            [r'(.*) callback plugin', 'lib/ansible/plugins/callback'],
            [r'(.*)\.py callback', 'lib/ansible/plugins/callback'],
            [r'callback plugin (.*)', 'lib/ansible/plugins/callback'],
            [r'(.*) stdout callback', 'lib/ansible/plugins/callback'],
            [r'stdout callback (.*)', 'lib/ansible/plugins/callback'],
            [r'stdout_callback (.*)', 'lib/ansible/plugins/callback'],
            [r'(.*) callback plugin', 'lib/ansible/plugins/callback'],
            [r'(.*) connection plugin', 'lib/ansible/plugins/connection'],
            [r'(.*) connection type', 'lib/ansible/plugins/connection'],
            [r'(.*) connection', 'lib/ansible/plugins/connection'],
            [r'(.*) transport', 'lib/ansible/plugins/connection'],
            [r'connection=(.*)', 'lib/ansible/plugins/connection'],
            [r'connection: (.*)', 'lib/ansible/plugins/connection'],
            [r'connection (.*)', 'lib/ansible/plugins/connection'],
            [r'strategy (.*)', 'lib/ansible/plugins/strategy'],
            [r'(.*) strategy plugin', 'lib/ansible/plugins/strategy'],
            [r'(.*) module util', 'lib/ansible/module_utils'],
            [r'ansible-galaxy (.*)', 'lib/ansible/galaxy'],
            [r'ansible-playbook (.*)', 'lib/ansible/playbook'],
            [r'ansible/module_utils/(.*)', 'lib/ansible/module_utils'],
            [r'module_utils/(.*)', 'lib/ansible/module_utils'],
            [r'lib/ansible/module_utils/(.*)', 'lib/ansible/module_utils'],
            [r'(\S+) documentation fragment', 'lib/ansible/utils/module_docs_fragments'],
        ]

        #_body = body
        #for SC in self.STOPCHARS:
        #    if SC in body:
        #        body = body.replace(SC, '')
        #body = body.strip()
        body = self.clean_body(body)

        matches = []

        for pattern in patterns:
            #logging.debug('test pattern: {}'.format(pattern))
            mobj = re.match(pattern[0], body, re.M | re.I)

            if mobj:
                logging.debug('pattern hit: {}'.format(pattern))
                fname = mobj.group(1)
                fname = fname.lower()

                fpath = os.path.join(pattern[1], fname)

                #if fpath in self.file_indexer.files:
                if fpath in self.gitrepo.files:
                    matches.append(fpath)
                #elif os.path.join(pattern[1], fname + '.py') in self.file_indexer.files:
                elif os.path.join(pattern[1], fname + '.py') in self.gitrepo.files:
                    fname = os.path.join(pattern[1], fname + '.py')
                    matches.append(fname)
                else:
                    # fallback to the directory
                    matches.append(pattern[1])

        return matches

    def search_by_tracebacks(self, body):

        matches = []

        if 'Traceback (most recent call last)' in body:
            lines = body.split('\n')
            for line in lines:
                line = line.strip()
                if line.startswith('DistributionNotFound'):
                    matches = ['setup.py']
                    break
                elif line.startswith('File'):
                    fn = line.split()[1]
                    for SC in self.STOPCHARS:
                        fn = fn.replace(SC, '')
                    if 'ansible_module_' in fn:
                        fn = os.path.basename(fn)
                        fn = fn.replace('ansible_module_', '')
                        matches = [fn]
                    elif 'cli/playbook.py' in fn:
                        fn = 'lib/ansible/cli/playbook.py'
                    elif 'module_utils' in fn:
                        idx = fn.find('module_utils/')
                        fn = 'lib/ansible/' + fn[idx:]
                    elif 'ansible/' in fn:
                        idx = fn.find('ansible/')
                        fn1 = fn[idx:]

                        if 'bin/' in fn1:
                            if not fn1.startswith('bin'):

                                idx = fn1.find('bin/')
                                fn1 = fn1[idx:]

                                if fn1.endswith('.py'):
                                    fn1 = fn1.rstrip('.py')

                        elif 'cli/' in fn1:
                            idx = fn1.find('cli/')
                            fn1 = fn1[idx:]
                            fn1 = 'lib/ansible/' + fn1

                        elif 'lib' not in fn1:
                            fn1 = 'lib/' + fn1

                        if fn1 not in self.files:
                            pass

        return matches

    def search_by_filepath(self, body, partial=False, context=None):
        """Find known filepaths in body"""

        matches = []
        body = self.clean_body(body)
        #logging.debug('search filepath [{}]: {}'.format(context, body))

        if not body:
            return []
        if body.lower() in self.STOPCHARS:
            return []
        if body.lower() in self.STOPWORDS:
            return []

        # 'inventory manager' vs. 'inventory/manager'
        if partial and ' ' in body:
            body = body.replace(' ', '/')

        if 'site-packages' in body:
            res = re.match('(.*)/site-packages/(.*)', body)
            body = res.group(2)
        if 'modules/core/' in body:
            body = body.replace('modules/core/', 'modules/')
        if 'modules/extras/' in body:
            body = body.replace('modules/extras/', 'modules/')
        if 'ansible-modules-core/' in body:
            body = body.replace('ansible-modules-core/', '/')
        if 'ansible-modules-extras/' in body:
            body = body.replace('ansible-modules-extras/', '/')
        if body.startswith('ansible/lib/ansible'):
            body = body.replace('ansible/lib', 'lib')
        if body.startswith('ansible/') and not body.startswith('ansible/modules'):
            body = body.replace('ansible/', '', 1)
        if 'module/' in body:
            body = body.replace('module/', 'modules/')

        logging.debug('search filepath [{}] [{}]: {}'.format(context, partial, body))
        #print('search filepath [{}] [{}]: {}'.format(context, partial, body))
        if len(body) < 2:
            return []

        body_paths = body.split('/')

        if not context or 'lib/ansible/modules' in context:
            mmatch = self.find_module_match(body)
            if mmatch:
                if isinstance(mmatch, list):
                    return [x['repo_filename'] for x in mmatch]
                else:
                    return [mmatch['repo_filename']]

        if body in self.gitrepo.files:
            matches = [body]
        else:
            #for fn in self.FILE_NAMES:
            for fn in self.gitrepo.files:

                # limit the search set if a context is given
                if context is not None and not fn.startswith(context):
                    continue

                if fn.endswith(body) or fn.endswith(body + '.py') or fn.endswith(body + '.ps1'):
                    # ios_config.py -> test_ios_config.py vs. ios_config.py
                    bn1 = os.path.basename(body)
                    bn2 = os.path.basename(fn)
                    if bn2.startswith(bn1):
                        matches = [fn]
                        break

                '''
                fn_paths = fn.split('/')
                if body in fn_paths:
                    matches.append(fn)
                    if 'ec2.py' in body:
                        import epdb; epdb.st()
                '''

                if partial:

                    # netapp_e_storagepool storage module
                    # lib/ansible/modules/storage/netapp/netapp_e_storagepool.py

                    # if all subpaths are in this filepath, it is a match
                    bp_total = 0
                    fn_paths = fn.split('/')
                    fn_paths.append(fn_paths[-1].replace('.py', '').replace('.ps1', ''))

                    for bp in body_paths:
                        if bp in fn_paths:
                            bp_total += 1

                    if bp_total == len(body_paths):
                        matches = [fn]
                        break

                    elif bp_total > 1:

                        if (float(bp_total) / float(len(body_paths))) >= (2.0 / 3.0):
                            if fn not in matches:
                                matches.append(fn)
                                #break

        if matches:
            tr = []
            for match in matches[:]:
                # reduce to longest path
                for m in matches:
                    if match == m:
                        continue
                    if len(m) < match and match.startswith(m):
                        tr.append(m)

            for r in tr:
                if r in matches:
                    logging.debug('trimming {}'.format(r))
                    matches.remove(r)

        matches = sorted(set(matches))
        logging.debug('return: {}'.format(matches))

        #if 'validate-modules' in body:
        #    import epdb; epdb.st()

        return matches

    def reduce_filepaths(self, matches):

        # unique
        _matches = []
        for _match in matches:
            if _match not in _matches:
                _matches.append(_match)
        matches = _matches[:]

        # squash to longest path
        if matches:
            tr = []
            for match in matches[:]:
                # reduce to longest path
                for m in matches:
                    if match == m:
                        continue
                    if m is None or match is None:
                        continue
                    if len(m) < match and match.startswith(m) or match.endswith(m):
                        tr.append(m)

            for r in tr:
                if r in matches:
                    matches.remove(r)
        return matches

    def include_modules_from_test_targets(self, matches):
        """Map test targets to the module files"""
        new_matches = []
        for match in matches:
            if not match:
                continue
            # include modules from test targets
            if 'test/integration/targets' in match:
                paths = match.split('/')
                tindex = paths.index('targets')
                mname = paths[tindex+1]
                #mrs = self.module_indexer.find_match(mname, exact=True)
                mrs = self.find_module_match(mname)
                if mrs:
                    if not isinstance(mrs, list):
                        mrs = [mrs]
                    for mr in mrs:
                        new_matches.append(mr['repo_filename'])
                #import epdb; epdb.st()
        return new_matches

    def get_meta_for_file(self, filename):
        meta = {
            'repo_filename': filename,
            'name': os.path.basename(filename).split('.')[0],
            'notify': [],
            'assign': [],
            'maintainers': [],
            'labels': [],
            'ignore': [],
            #'keywords': [],
            'support': None,
            'deprecated': False,
        }

        if filename in self.BOTMETA['files']:
            fdata = self.BOTMETA['files'][filename].copy()
            if 'maintainers' in fdata:
                meta['notify'] += fdata['maintainers']
                meta['assign'] += fdata['maintainers']
                meta['maintainers'] += fdata['maintainers']
            if 'notify' in fdata:
                meta['notify'] += fdata['notify']
            if 'labels' in fdata:
                meta['labels'] += fdata['labels']
            if 'ignore' in fdata:
                meta['ignore'] += fdata['ignore']
            #if 'keywords' in fdata:
            #    meta['keywords'] += fdata['keywords']
            if 'support' in fdata:
                if isinstance(fdata['support'], list):
                    meta['support'] = fdata['support'][0]
                else:
                    meta['support'] = fdata['support']
            if 'deprecated' in fdata:
                meta['deprecated'] = fdata['deprecated']

        # walk up the tree for more meta
        paths = filename.split('/')
        for idx,x in enumerate(paths):
            idx -= 1
            #logging.debug(idx)
            if idx < 1:
                continue
            thispath = '/'.join(paths[:(0-idx)])
            if thispath in self.BOTMETA['files']:
                fdata = self.BOTMETA['files'][thispath].copy()
                if 'support' in fdata and not meta['support']:
                    if isinstance(fdata['support'], list):
                        meta['support'] = fdata['support'][0]
                    else:
                        meta['support'] = fdata['support']
                #if 'keywords' in fdata:
                #    meta['keywords'] += fdata['keywords']
                if 'labels' in fdata:
                    meta['labels'] += fdata['labels']
                if 'maintainers' in fdata:
                    meta['notify'] += fdata['maintainers']
                    meta['assign'] += fdata['maintainers']
                    meta['maintainers'] += fdata['maintainers']
                if 'ignore' in fdata:
                    meta['ignore'] += fdata['ignore']
                if 'notify' in fdata:
                    meta['notify'] += fdata['notify']
                #import epdb; epdb.st()

        # clean up the result
        _meta = meta.copy()
        for k,v in _meta.items():
            if isinstance(v, list):
                meta[k] = sorted(set(v))

        return meta

    def _get_meta_for_file(self, filename):
        """Compile metadata for a matched filename"""

        meta = {
            'repo_filename': filename
        }

        meta['labels'] = self.file_indexer.get_filemap_labels_for_files([filename])
        (to_notify, to_assign) = self.file_indexer.get_filemap_users_for_files([filename])
        meta['notify'] = to_notify
        meta['assign'] = to_assign

        if 'lib/ansible/modules' in filename:
            mmeta = self.module_indexer.find_match(filename, exact=True)
            if not mmeta:
                pass
            elif mmeta and len(mmeta) == 1:
                meta.update(mmeta[0])
            else:
                import epdb; epdb.st()

        #import epdb; epdb.st()
        return meta

    def find_module_match(self, pattern):
        '''Exact module name matching'''

        logging.debug('find_module_match for "{}"'.format(pattern))
        candidate = None

        BLACKLIST = [
            'module_utils',
            'callback',
            'network modules',
            'networking modules'
            'windows modules'
        ]

        if not pattern or pattern is None:
            return None

        # https://github.com/ansible/ansible/issues/19755
        if pattern == 'setup':
            pattern = 'lib/ansible/modules/system/setup.py'

        if '/facts.py' in pattern or ' facts.py' in pattern:
            pattern = 'lib/ansible/modules/system/setup.py'

        # https://github.com/ansible/ansible/issues/18527
        #   docker-container -> docker_container
        if '-' in pattern:
            pattern = pattern.replace('-', '_')

        if 'module_utils' in pattern:
            # https://github.com/ansible/ansible/issues/20368
            return None
        elif 'callback' in pattern:
            return None
        elif 'lookup' in pattern:
            return None
        elif 'contrib' in pattern and 'inventory' in pattern:
            return None
        elif pattern.lower() in BLACKLIST:
            return None

        candidate = self._find_module_match(pattern)
        #if 'jabber' in pattern:
        #    import epdb; epdb.st()

        if not candidate:
            candidate = self._find_module_match(os.path.basename(pattern))

        if not candidate and '/' in pattern and not pattern.startswith('lib/'):
            ppy = None
            ps1 = None
            if not pattern.endswith('.py') and not pattern.endswith('.ps1'):
                ppy = pattern + '.py'
            if not pattern.endswith('.py') and not pattern.endswith('.ps1'):
                ps1 = pattern + '.ps1'
            for mf in self.gitrepo.module_files:
                if pattern in mf:
                    if mf.endswith(pattern) or mf.endswith(ppy) or mf.endswith(ps1):
                        candidate = mf
                        break

        return candidate

    def _find_module_match(self, pattern):

        logging.debug('matching on {}'.format(pattern))

        matches = []

        if isinstance(pattern, unicode):
            pattern = pattern.encode('ascii', 'ignore')

        logging.debug('_find_module_match: {}'.format(pattern))

        noext = pattern.replace('.py', '').replace('.ps1', '')

        for k,v in self.MODULES.items():
            if v['name'] in [pattern, '_' + pattern, noext, '_' + noext]:
                logging.debug('match {} on name: {}'.format(k, v['name']))
                matches = [v]
                break

        if not matches:
            # search by key ... aka the filepath
            for k,v in self.MODULES.items():
                if k == pattern:
                    logging.debug('match {} on key: {}'.format(k, k))
                    matches = [v]
                    break

        return matches
