import re
    MERGE_CRE = re.compile('^(<<<<<<<|>>>>>>>).*$')
            fstat = os.stat(name)
            self.old_mode = fstat.st_mode
            self.timestamp = fstat.st_mtime
            self.timestamp = 0
        self.new_mode = self.old_mode
        self.binary = False
            return self.timestamp < os.path.getmtime(self.name) or self.new_mode is None
            return self.new_mode is not None or self.timestamp < 0
    def has_unresolved_merges(self):
        if os.path.exists(self.name):
            for line in open(self.name).readlines():
                if _FileData.MERGE_CRE.match(line):
                    return True
        return False
_PTS_TEMPL = '%Y-%m-%d %H:%M:%S.{0:09} ' + _pts_tz_str()

def _pts_str(secs=None):
    '''Return the "in patch" timestamp string for "secs" seconds'''
    ts_str = time.strftime(_PTS_TEMPL, time.localtime(secs))
    return ts_str.format(int((secs % 1) * 1000000000))

_PTS_ZERO = _pts_str(0)

def _pts_for_path(path):
    '''Return the "in patch" timestamp string for "secs" seconds'''
    return _pts_str(os.path.getmtime(path))
            return
        patch_cmd = ['patch', '--merge', '--force', '-p1', '--batch',]
            patch_ok = True
            if file_data.binary is not False:
                if file_data.new_mode is not None:
                    open(file_data.name, 'wb').write(file_data.binary)
                elif os.path.exists(file_data.name):
                    os.remove(file_data.name)
            elif file_data.diff:
                result = runext.run_cmd(patch_cmd + [file_data.name], file_data.diff)
                patch_ok = result.ecode == 0
                patch_ok = patch_ok and file_data.new_mode is None
            bu_f_dir = os.path.dirname(bu_f_name)
            if not os.path.exists(bu_f_dir):
                os.makedirs(bu_f_dir)
        def do_diff(labels, operands):
            return runext.run_cmd(['diff', '-u', '--binary', '-p'] + labels + operands)
            if file_data.has_unresolved_merges():
                # ensure this file shows up as needing refresh
                file_data.timestamp = -1
                dump_db()
                return runext.Result(3, '', 'File has unresolved merge(s).\n')
                labels = ['--label={0} {1}'.format(os.path.join('a', filename), _pts_for_path(bu_f_name))]
                operands = [bu_f_name, filename]
                labels = ['--label=/dev/null {0}'.format(_PTS_ZERO)]
                operands = ['/dev/null', filename]
            labels.append('--label={0} {1}'.format(os.path.join('b', filename), _pts_for_path(filename)))
            result = do_diff(labels, operands)
            if result.stderr:
                assert result.ecode > 1
                # ensure this file shows up as needing refresh
                file_data.timestamp = -1
                if result.ecode <= 2:
                    result = runext.Result(3, result.stdout, result.stderr)
            else:
                stat_data = os.stat(filename)
                file_data.new_mode = stat_data.st_mode
                file_data.timestamp = stat_data.st_mtime
                if result.ecode < 2:
                    file_data.diff = result.stdout
                    file_data.binary = False
                else:
                    file_data.diff = None
                    file_data.binary = open(filename, 'rb').read()
            labels = ['--label={0} {1}'.format(os.path.join('a', filename), _pts_for_path(bu_f_name)),
                '--label=/dev/null {0}'.format(_PTS_ZERO)]
            operands = [bu_f_name, '/dev/null']
            result = do_diff(labels, operands)
            if result.stderr:
                assert result.ecode > 1
                file_data.new_mode = None
                # ensure this file shows up as needing refresh
                file_data.timestamp = -1
                if result.ecode <= 2:
                    result = runext.Result(3, result.stdout, result.stderr)
            else:
                file_data.new_mode = None
                file_data.timestamp = 0
                if result.ecode < 2:
                    file_data.diff = result.stdout
                    file_data.binary = False
                else:
                    file_data.diff = None
                    file_data.binary = True
            result = runext.Result(0, '', 'File "{0}" does not exist\n'.format(filename))
    def do_import_patch(self, epatch, name):
        '''Import an external patch with the given name (after the top patch)'''
        assert is_writable()
        assert self.get_series_index(name) is None
        descr = utils.make_utf8_compliant(epatch.get_description())
        patch = _PatchData(name, descr)
        for diff_plus in epatch.diff_pluses:
            path = diff_plus.get_file_path(epatch.num_strip_levels)
            patch.do_add_file(path)
            patch.files[path].diff = str(diff_plus.diff)
            for preamble in diff_plus.preambles:
                if preamble.preamble_type == 'git':
                    for key in ['new mode', 'new file mode']:
                        if key in preamble.extras:
                            patch.files[path].new_mode = int(preamble.extras[key], 8)
                            break
                    break
        self._do_insert_patch(patch)
def import_patch(epatch, name):
    '''Import an external patch with the given name (after the top patch)'''
    assert is_writable()
    assert get_patch_series_index(name) is None
    _DB.do_import_patch(epatch, name)
