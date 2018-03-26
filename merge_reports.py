#!/usr/bin/env python
'''
Created on Jun 29, 2015

@author: rousef
'''

import os.path
import sys
import time
import calendar
import subprocess

#Booleans
DEBUG = ''
CHART_TITLE = ''
CATCHUP_CHART= ''
REINTEGRATE_CHART= ''
SKIP_REINTEGRATE_MERGE= ''

#Time based variables
SECONDS_IN_A_DAY=86400
SVN_TIME_DATE_FORMAT  = '%Y-%m-%d %H:%M:%S'
FILE_TIMESTAMP_FORMAT = '%Y-%m-%d_%H_%M_%S'
CURRENT_EPOCH_SECONDS=calendar.timegm(time.gmtime())
REPORT_GENERATED_TIME=time.strftime(FILE_TIMESTAMP_FORMAT)

#Strings
HTML_REPORT_FILE_NAME = 'merge_report'
SVNROOT = 'https://teamforge-vce.usd.lab.emc.com/svn/repos/'
CRUCIBLE_CHANGELOG='https://crucible.ent.vce.com/changelog/'


#Status
RED    ='#FF0033'
GREEN  ='#009933'
YELLOW ='#FFFF00'
RED_HIGHLIGHT    ='#FF6666'
GREEN_HIGHLIGHT  ='#669900'
YELLOW_HIGHLIGHT ='#FFFF99'
MERGE_STATUS_OVERDUE ='RED'
MERGE_STATUS_GOOD    ='GREEN'
MERGE_STATUS_NEEDED  ='YELLOW'

crucible_to_svn_repository_mapping = {'compliance'                       :'Vision_Compliance',
                                      'converged_shell'                  :'Vision_Converged_Shell',
                                      'dds'                              :'Vision_DDS',
                                      'devops'                           :'Vision_DevOps',
                                      'fm'                               :'Vision_Foundation_Management',
                                      'panorama'                         :'Vision_Panorama',
                                      'sdk'                              :'Vision_SDK',
                                      'services'                         :'Vision_Services',
                                      'support'                          :'Vision_Support',
                                      'tech_alerts'                      :'Vision_Tech_Alerts',
                                      'vcops'                            :'Vision_VCops',
                                      'vsphere-plugin'                   :'Vision_VSphere_Plugin',
                                      'webui'                            :'Vision_WebUI'}


def mergeinfo(source, target, repo):
    merge_info_command = 'svn mergeinfo ' + SVNROOT + repo + '/' + source + ' ' + SVNROOT + repo + '/' + target
    p = subprocess.Popen(merge_info_command, stdout=subprocess.PIPE, shell=True)
    (output, err) = p.communicate()
    return output.splitlines()[5].split()

def commits_available_for_merge(source, target, repo):
    merge_info_command = 'svn mergeinfo --show-revs eligible ' + SVNROOT + repo + '/' + source + ' ' + SVNROOT + repo + '/' + target
    p = subprocess.Popen(merge_info_command, stdout=subprocess.PIPE, shell=True)
    (output, err) = p.communicate()
    return output.splitlines()

def revision_info(repo, revision):
    revision_info_command = 'svn log --quiet --revision ' + revision + ' ' + SVNROOT + repo
    p = subprocess.Popen(revision_info_command, stdout=subprocess.PIPE, shell=True)
    (output, err) = p.communicate()
    return output.splitlines()[1].split()

def revision_info_comments(repo, revision):
    revision_info_command = 'svn log --revision ' + revision + ' ' + SVNROOT + repo
    p = subprocess.Popen(revision_info_command, stdout=subprocess.PIPE, shell=True)
    (output, err) = p.communicate()
    return output.splitlines()

def commits_since_revision_info(repo, revision, branch):
    revision_info_command = 'svn log --quiet --revision ' + revision + ':HEAD ' + SVNROOT + repo + '/' + branch
    p = subprocess.Popen(revision_info_command, stdout=subprocess.PIPE, shell=True)
    (output, err) = p.communicate()
    return output.splitlines()

# We now have a dependency on the utility http://wkhtmltopdf.org/downloads.html
# It must be installed if a static image is to be created.
def create_static_report_image():
    html_to_image_command = 'wkhtmltoimage --crop-h 505 --crop-w 855 --javascript-delay 4000 merge_report.html merge_report.png'
    p = subprocess.Popen(html_to_image_command, stdout=subprocess.PIPE, shell=True)
    (output, err) = p.communicate()
    return output.splitlines()


# Pull out and parse the svn log information for a single revision
# Example output from svn log command below
#------------------------------------------------------------------------
#r20283 | kerbam | 2015-12-11 15:33:56 -0500 (Fri, 11 Dec 2015) | 3 lines
#
#US17373: Update build scripts to pull RPMs from Artifactory at build time.
#
#Merged changes from sandbox for artifact resolution from artifactory instead of vmstudio.
#------------------------------------------------------------------------
def parse_single_revision_log(revision_log):
    revision_info = {}
    revision = ''
    author = ''
    date = ''
    time = ''
    comments = []
    first_empty_line = True
    dash_separator = '------------------------------------------------------------------------'

    # Skip the first line as it should always be a line separator
    for line in revision_log[1:]:
        if line == dash_separator:
            revision_info.update({'comments':comments})
        else:
            if line == '' and first_empty_line:
                first_empty_line = False
                continue
            # If the revision information hasn't been parsed yet.
            elif not revision:
                revision_split = line.split()
                revision = revision_split[0]
                author   = revision_split[2]
                date     = revision_split[4]
                time     = revision_split[5]
                timezone = revision_split[6]
            else:
                comments.append(line)
    revision_info.update({'revision':revision})
    revision_info.update({'author':author})
    revision_info.update({'date':date})
    revision_info.update({'time':time})
    return revision_info


def calc_merge_info(repos, source, target):
    merge_info = []
    # Loop through all of the repos and generate data as you go.
    for repo in repos:
        # merge_status logic
        # If there are no revisions available for merge the status will remain GOOD.
        # If there is at least 1 revision available for merge the status moves to NEEDED.
        # If either the elapsed days since the first revision available for merge exceeds
        # the MERGE_OVERDUE_DAYS value or the number of revisions available for merge exceeds
        # the MERGE_OVERDUE_COMMITS the status will be changed to OVERDUE
        merge_status = MERGE_STATUS_GOOD

        # Create holder values in case there are no revisions available for merge and we never
        # instantiate values for the variables.
        revisions_available_for_merge = [];
        first_revision_eligible_for_merge_date_string = ''

        repo = repo.strip()
        if DEBUG:
            print ''
            print 'Working with repo "' + repo + '"'

        revisions_available_for_merge = commits_available_for_merge(source, target, repo)
        print 'repo ' + repo + ' revisions available for merge ' + str(revisions_available_for_merge)

        # Create a number variable as it is used in a number of places.
        number_of_revisions_available_for_merge = len(revisions_available_for_merge)
        if DEBUG:
            print 'Number of revisions available for merge = ' + str(number_of_revisions_available_for_merge)

        if number_of_revisions_available_for_merge > merge_warning_commits_threshold:
            merge_status = MERGE_STATUS_NEEDED

            first_revision_eligible_for_merge_info = revision_info(repo, revisions_available_for_merge[0])

            if DEBUG:
                print 'The first_revision_eligible_for_merge_info = ' + str(first_revision_eligible_for_merge_info)

            first_revision_eligible_for_merge_date_string = first_revision_eligible_for_merge_info[4] + ' ' + first_revision_eligible_for_merge_info[5]

            if DEBUG:
                print 'The reivision_date_string = ' + first_revision_eligible_for_merge_date_string

            first_elibile_merge_revision_seconds_since_epoch = calendar.timegm(time.strptime(first_revision_eligible_for_merge_date_string, SVN_TIME_DATE_FORMAT))

            if DEBUG:
                print 'The first_elibile_merge_revision_seconds_since_epoch = ' + str(first_elibile_merge_revision_seconds_since_epoch)

            days_since_first_eligible_merge_revision = (CURRENT_EPOCH_SECONDS - first_elibile_merge_revision_seconds_since_epoch)/SECONDS_IN_A_DAY

            if DEBUG:
                print 'days_since_first_eligible_merge_revision = ' + str(days_since_first_eligible_merge_revision)

            if days_since_first_eligible_merge_revision > merge_overdue_days_threshold:
                merge_status = MERGE_STATUS_OVERDUE
        if number_of_revisions_available_for_merge > merge_warning_commits_threshold and merge_status == MERGE_STATUS_GOOD:
            merge_status = MERGE_STATUS_NEEDED
        if number_of_revisions_available_for_merge > merge_overdue_commits_threshold:
            merge_status = MERGE_STATUS_OVERDUE
        merge_info.append([repo, merge_status, first_revision_eligible_for_merge_date_string, number_of_revisions_available_for_merge, revisions_available_for_merge])
    return merge_info

def write_report_header(report_file, report_title, feature_branch, integration_branch, total_catchup_merges, total_reintegrate_merges):

    report_file.write('<!doctype html>\n')
    report_file.write('<html>\n')
    report_file.write('  <head>\n')
    report_file.write('    <title>' + report_title + '</title>\n')
    report_file.write('    <script src="Chart.js"></script>\n')
    report_file.write('    <script src="sortable.js"></script>\n')
    report_file.write('    <link rel="shortcut icon" href="doughnut_chart_icon.png">\n')
    report_file.write('    <link rel="stylesheet" type="text/css" href="report.css">\n')
    report_file.write('  <body>\n')
    report_file.write('    <h1>' + report_title + '</h1>\n')
    report_file.write('    <table class="headpanel">\n')
    report_file.write('      <tr>\n')
    report_file.write('      <tr style="background: white;">\n')
    if CATCHUP_CHART:
        report_file.write('        <td>\n')
        report_file.write('          <div style="width: 400px; height: 400px; float: left; position: relative;">\n')
        report_file.write('          <div style="width: 100%; height: 40px; position: absolute; top: 50%; left: 0; margin-top: -20px; line-height:19px; text-align: center; z-index: 999999999999999">\n')
        if total_catchup_merges == 0:
            report_file.write('          <h3>Congratulations. No merges needed.<Br/>You bestride the software world like a<Br/>Colossus!</h3>\n')
        else:
            report_file.write('          <h4>Total Revisions to Merge<Br/>' + str(total_catchup_merges) + '</h4>\n')
        report_file.write('          </div>\n')
        report_file.write('          <canvas id="catchup_merge" width="400" height="400"></canvas>\n')
        report_file.write('          <h3 class="charttitle">Catch up merges</h3>\n')
        report_file.write('          <h4 class="charttitle"> ' + integration_branch + ' => ' + feature_branch + ' </h4>\n')
        report_file.write('        </td>\n')
    if REINTEGRATE_CHART:
        report_file.write('        <td>\n')
        report_file.write('          <div style="width: 400px; height: 400px; float: left; position: relative;">\n')
        report_file.write('          <div style="width: 100%; height: 40px; position: absolute; top: 50%; left: 0; margin-top: -20px; line-height:19px; text-align: center; z-index: 999999999999999">\n')
        if total_reintegrate_merges == 0:
            report_file.write('          <h3>Congratulations. No merges needed.<Br/>You bestride the software world like a<Br/>Colossus!</h3>\n')
        else:
            report_file.write('          <h4>Total Revisions to Merge<Br />' + str(total_reintegrate_merges) + '</h4>\n')
        report_file.write('          </div>\n')
        report_file.write('          <canvas id="reintegrate_merge" width="400" height="400"></canvas>\n')
        report_file.write('          <h3 class="charttitle">Reintegrate merges</h3>\n')
        report_file.write('          <h4 class="charttitle"> ' + feature_branch + ' => ' + integration_branch + ' </h4>\n')
        report_file.write('        </td>\n')
    report_file.write('      </tr>\n')
    report_file.write('    </table>\n')
    report_file.write('    <br>\n')
    report_file.write('    <br>\n')
    report_file.write('    <br>\n')
    report_file.write('    <br>\n')
    report_file.write('    <a href="https://wiki.ent.vce.com/display/VIO/Merge+Report+Information">Merge Report Information</a>\n')
    report_file.write('    <br>\n')

def create_commit_table(report_file, commit_info):
    report_file.write('  <table class="sortable" border=1>\n')
    report_file.write('    <thead>\n')
    report_file.write('      <tr style="color: black; background: lightgray;">\n')
    report_file.write('        <th width="240">Repository</th>\n')
    report_file.write('        <th>Revision</th>\n')
    report_file.write('        <th width="80">Author</th>\n')
    report_file.write('        <th width="140">Date Time</th>\n')
    report_file.write('        <th>Comments</th>\n')
    report_file.write('      </tr>\n')
    report_file.write('    </thead>\n')
    report_file.write('    <tbody>\n')
    for repo_info in commit_info:
        repo = repo_info[0]
        # In case there are repos further down the directory listing as in compliance/compliance-master
        repo = repo.split('/')[0]
        crucible_repo = crucible_to_svn_repository_mapping.get(repo)
        revision_available_for_merge = repo_info[4]
        for revision in revision_available_for_merge:
            revision_log_lines = revision_info_comments(repo, revision[1:])
            revision_info = parse_single_revision_log(revision_log_lines)
            report_file.write('      <tr>\n')
            report_file.write('        <td>' + repo +'</td>\n')
            report_file.write('        <td> <a href="' + CRUCIBLE_CHANGELOG + crucible_repo + '?cs=' + revision[1:] + '">' + revision[1:] +'</td>\n')
            report_file.write('        <td>' + revision_info['author'] +'</td>\n')
            report_file.write('        <td>' + revision_info['date'] + ' ' + revision_info['time'] + '</td>\n')
            comments = revision_info['comments']
            comment_lines = []
            comment_lines = comments[0]
            for comment in comments[1:]:
                comment_lines = comment_lines + '/n' + comment
            report_file.write('        <td>' + comment_lines + '</td>\n')
            report_file.write('      </tr>\n')
    report_file.write('    </tbody>\n')
    report_file.write('  </table>\n')

def write_report_commit_tables(report_file, feature_branch, integration_branch, catch_up_merge_info_merge_info, total_catchup_merges, reintegrate_merge_info, total_reintegrate_merges):
    report_file.write('<h5>Number of commits to merge.</h5>\n')
    report_file.write('  <table class="sortable" border=1>\n')
    report_file.write('    <thead>\n')
    report_file.write('      <tr style="color: black; background: lightgray;">\n')
    report_file.write('        <th>Merge Type</th>\n')
    report_file.write('        <th>Number of Commits to Merge</th>\n')
    report_file.write('      </tr>\n')
    report_file.write('    </thead>\n')
    report_file.write('    <tbody>\n')
    if CATCHUP_CHART:
        report_file.write('      <tr>\n')
        report_file.write('        <td><a href="#catchup">Catchup Merges</td>\n')
        report_file.write('        <td>' + str(total_catchup_merges) +'</td>\n')
        report_file.write('      </tr>\n')
    if REINTEGRATE_CHART:
        report_file.write('      <tr>\n')
        report_file.write('        <td><a href="#reintegrate">Reintegrate Merges</td>\n')
        report_file.write('        <td>' + str(total_reintegrate_merges) +'</td>\n')
        report_file.write('      </tr>\n')
    report_file.write('    </tbody>\n')
    report_file.write('  </table>\n')
    report_file.write('    <br>\n')
    if CATCHUP_CHART:
        report_file.write('    <br>\n')
        report_file.write('    <br>\n')
        report_file.write('    <a name ="catchup"></a>\n')
        report_file.write('  <h5>All Commits for the Catchup Merge</h5>\n')
        create_commit_table(report_file, catch_up_merge_info_merge_info)
    if REINTEGRATE_CHART:
        report_file.write('    <br>\n')
        report_file.write('    <br>\n')
        report_file.write('    <a name ="reintegrate"></a>\n')
        report_file.write('  <h5>All Commits for the Reintegrate Merge</h5>\n')
        create_commit_table(report_file, reintegrate_merge_info)


def write_report_var_data(report_file, var_type, var_data, merge_count):
    report_file.write('          var ' + var_type + ' = [\n')
    if merge_count == 0:
        report_file.write('              {\n')
        report_file.write('                  value: 1,\n')
        report_file.write('                  color: "' + GREEN + '",\n')
        report_file.write('                  highlight: "' + GREEN_HIGHLIGHT + '",\n')
        report_file.write('                  label: "All repos up to date"\n')
        report_file.write('              },\n')
    else:
# Just to keep in mind the order of the merge info list objects
#merge_info.append([repo, merge_status, first_revision_eligible_for_merge_date_string, number_of_revisions_available_for_merge, revisions_available_for_merge])
        for data in var_data:
            report_file.write('              {\n')
            report_file.write('                  value: ' + str(data[3]) + ',\n')
            if data[1] == MERGE_STATUS_GOOD:
                report_file.write('                  color: "' + GREEN + '",\n')
                report_file.write('                  highlight: "' + GREEN_HIGHLIGHT + '",\n')
            if data[1] == MERGE_STATUS_NEEDED:
                report_file.write('                  color: "' + YELLOW + '",\n')
                report_file.write('                  highlight: "' + YELLOW_HIGHLIGHT + '",\n')
            if data[1] == MERGE_STATUS_OVERDUE:
                report_file.write('                  color: "' + RED + '",\n')
                report_file.write('                  highlight: "' + RED_HIGHLIGHT + '",\n')
            report_file.write('                  label: "' + data[0] + '"\n')
            report_file.write('              },\n')
    report_file.write('              ];\n')

def write_report_script(report_file, catchup_merge_info, total_catchup_revisions_that_need_merging, reintegrate_merge_info, total_reintegrate_revisions_that_need_merging):
    report_file.write('      <script>\n')
    if CATCHUP_CHART:
        write_report_var_data(report_file, 'catchup_merge_data', catch_up_merge_info, total_catchup_revisions_that_need_merging)
    if REINTEGRATE_CHART:
        write_report_var_data(report_file, 'reintegrate_merge_data', reintegrate_merge_info, total_reintegrate_revisions_that_need_merging)
    report_file.write('        window.onload = function(){\n')
    if CATCHUP_CHART:
        report_file.write('          var ctx = document.getElementById("catchup_merge").getContext("2d");\n')
        report_file.write('          window.myDoughnut = new Chart(ctx).Doughnut(catchup_merge_data, {responsive : true});\n')
    if REINTEGRATE_CHART:
        report_file.write('          var ctx2 = document.getElementById("reintegrate_merge").getContext("2d");\n')
        report_file.write('          window.myDoughnut = new Chart(ctx2).Doughnut(reintegrate_merge_data, {responsive : true});\n')
    report_file.write('        };\n')
    report_file.write('      </script>\n')

def write_report_footer(report_file, feature_branch, integration_branch, merge_warning_days_threshold, merge_overdue_days_threshold, merge_warning_commits_threshold, merge_overdue_commits_threshold, repos, total_catchup_merges, total_reintegrate_merges):

    report_file.write('    <h5><preformatted>\n')
    report_file.write('            Report Generated: ' + REPORT_GENERATED_TIME        + '<br>\n')
    report_file.write('            Report Parameters below <br>\n')
    report_file.write('            MERGE_WARNING_DAYS    = ' + str(merge_warning_days_threshold) + '<br>\n')
    report_file.write('            MERGE_OVERDUE_DAYS    = ' + str(merge_overdue_days_threshold) + '<br>\n')
    report_file.write('            MERGE_WARNING_COMMITS = ' + str(merge_warning_commits_threshold)  + '<br>\n')
    report_file.write('            MERGE_OVERDUE_COMMITS = ' + str(merge_overdue_commits_threshold)  + '<br>\n')
    report_file.write('            INTEGRATION_BRANCH    = ' + integration_branch     + '<br>\n')
    report_file.write('            FEATURE_BRANCH        = ' + feature_branch         + '<br>\n')
    repo_string = ''
    for repo in repos:
        repo_string = repo_string + repo + ' '
    report_file.write('            REPOS                 = ' + repo_string + '\n')
    report_file.write('    </preformatted></h5>\n')
    report_file.write('\n')
    report_file.write('        </body>\n')
    report_file.write('</html>\n')

try:
    DEBUG = os.environ["DEBUG"]
    # In case this is passed from jenkins.
    if DEBUG == 'false':
        DEBUG=''
except KeyError:
    pass

# Used as a boolean to trigger html report
try:
    CHART_TITLE = os.environ["CHART_TITLE"]
except KeyError:
    pass

try:
    SKIP_REINTEGRATE_MERGE = os.environ["SKIP_REINTEGRATE_MERGE"]
except KeyError:
    pass

try:
    CATCHUP_CHART = os.environ["CATCHUP_CHART"]
    if CATCHUP_CHART == 'false':
        CATCHUP_CHART=''
except KeyError:
    pass

try:
    REINTEGRATE_CHART = os.environ["REINTEGRATE_CHART"]
    if REINTEGRATE_CHART == 'false':
        REINTEGRATE_CHART=''
except KeyError:
    pass

try:
    repos                           = os.environ["REPOS"].split(',')
    feature_branch                  = os.environ["FEATURE_BRANCH"]
    integration_branch              = os.environ["INTEGRATION_BRANCH"]
    merge_overdue_days_threshold    = int(os.environ["MERGE_OVERDUE_DAYS"])
    merge_warning_days_threshold    = int(os.environ["MERGE_WARNING_DAYS"])
    merge_overdue_commits_threshold = int(os.environ["MERGE_OVERDUE_COMMITS"])
    merge_warning_commits_threshold = int(os.environ["MERGE_WARNING_COMMITS"])
except KeyError:
    print 'The following environment variables must be set.'
    print ''
    print 'REPOS'
    print '                    example REPOS="compliance, fm, sdk"'
    print 'INTEGRATION_BRANCH'
    print '                    example INTEGRATION_BRANCH=branches/florence'
    print 'FEATURE_BRANCH'
    print '                    example FEATURE_BRANCH=branches/feature/florence_everest'
    print 'MERGE_OVERDUE_DAYS'
    print '                    example MERGE_OVERDUE_DAYS=28'
    print 'MERGE_WARNING_DAYS'
    print '                    example MERGE_WARNING_DAYS=14'
    print 'MERGE_OVERDUE_COMMITS'
    print '                    example MERGE_OVERDUE_COMMITS=20'
    print 'MERGE_WARNING_COMMITS'
    print '                    example MERGE_WARNING_COMMITS=10'
    sys.exit(1)

if DEBUG:
    print ''
    print 'Passed parameters'
    print 'REPOS                  = ' + str(repos)
    print 'FEATURE_BRANCH         = ' + feature_branch
    print 'INTEGRATION_BRANCH     = ' + integration_branch
    print 'MERGE_OVERDUE_COMMITS  = ' + str(merge_overdue_commits_threshold)
    print 'MERGE_WARNING_COMMITS  = ' + str(merge_overdue_commits_threshold)
    print 'MERGE_OVERDUE_DAYS     = ' + str(merge_overdue_days_threshold)
    print 'MERGE_WARNING_DAYS     = ' + str(merge_warning_days_threshold)
    if CHART_TITLE:
        print 'CHART_TITLE            = ' + CHART_TITLE
    if CATCHUP_CHART:
        print 'CATCHUP_CHART = ' + CATCHUP_CHART
    if REINTEGRATE_CHART:
        print 'REINTEGRATE_CHART = ' + REINTEGRATE_CHART
    if SKIP_REINTEGRATE_MERGE:
        print 'SKIP_REINTEGRATE_MERGE = ' + SKIP_REINTEGRATE_MERGE
    print ''
    print 'Constants'
    print 'SECONDS_IN_A_DAY       = ' + str(SECONDS_IN_A_DAY)
    print 'CURRENT_EPOCH_SECONDS  = ' + str(CURRENT_EPOCH_SECONDS)
    print 'SVN_TIME_DATE_FORMAT   = ' + SVN_TIME_DATE_FORMAT
    print 'SVNROOT                = ' + SVNROOT

# Sort the repos so that they always are generated in the same order
repos.sort()

print ''
print 'Report generated on ' + REPORT_GENERATED_TIME
print ''

catch_up_merge_info = calc_merge_info(repos, integration_branch, feature_branch)
print 'Catch up merge info for integration branch ' + integration_branch
print 'to feature branch ' + feature_branch
# Just to keep in mind the order of the merge info list objects
#merge_info.append([repo, merge_status, first_revision_eligible_for_merge_date_string, number_of_revisions_available_for_merge, revisions_available_for_merge])
total_catchup_revisions_that_need_merging=0
for merge_info in catch_up_merge_info:
    print ''
    print 'REPO:                                               ' + merge_info[0]
    print 'STATUS:                                             ' + merge_info[1]
    print 'DATE OF FIRST MERGE ELIGIBLE REVISION:              ' + merge_info[2]
    print 'NUMBER OF REVISIONS AVAILABLE FOR MERGE:            ' + str(merge_info[3])
    total_catchup_revisions_that_need_merging = total_catchup_revisions_that_need_merging + merge_info[3]

print ''
print 'TOTAL CATCH UP REVISIONS THAT NEED TO BE MERGED:    ' + str(total_catchup_revisions_that_need_merging)
print ''
print ''
print ''
sys.stdout.flush()

reintegrate_merge_info = calc_merge_info(repos, feature_branch, integration_branch)
print ''
print 'Reintegrate merge info for feature branch ' + feature_branch
print 'to integration branch ' + integration_branch 
# Just to keep in mind the order of the merge info list objects
#merge_info.append([repo, merge_status, first_revision_eligible_for_merge_date_string, number_of_revisions_available_for_merge, revisions_available_for_merge])
total_reintegrate_revisions_that_need_merging=0
for merge_info in reintegrate_merge_info:
    print ''
    print 'REPO:                                               ' + merge_info[0]
    print 'STATUS:                                             ' + merge_info[1]
    print 'DATE OF FIRST MERGE ELIGIBLE REVISION:              ' + merge_info[2]
    print 'NUMBER OF REVISIONS AVAILABLE FOR MERGE:            ' + str(merge_info[3])
    total_reintegrate_revisions_that_need_merging = total_reintegrate_revisions_that_need_merging + merge_info[3]
print ''
print 'TOTAL REINTEGRATE REVISIONS THAT NEED TO BE MERGED: ' + str(total_reintegrate_revisions_that_need_merging)
print ''
print ''
print 'Report generated on ' + REPORT_GENERATED_TIME
sys.stdout.flush()

if CHART_TITLE:
    print ''
    print ''
    print 'Creating HTML version of the report.'
    sys.stdout.flush()
    FULL_HTML_REPORT_FILE_NAME = HTML_REPORT_FILE_NAME + '.html'
    if os.path.isfile(FULL_HTML_REPORT_FILE_NAME):
        # Rename the previous generated report in case we need to examine history.
        last_report_modified_time = time.strftime(FILE_TIMESTAMP_FORMAT,time.localtime(int(round(os.path.getmtime(FULL_HTML_REPORT_FILE_NAME)))))
        os.rename(FULL_HTML_REPORT_FILE_NAME, HTML_REPORT_FILE_NAME + '_' + last_report_modified_time + '.html')
    report_file = open (FULL_HTML_REPORT_FILE_NAME, 'w')
    write_report_header(report_file, CHART_TITLE, feature_branch, integration_branch, total_catchup_revisions_that_need_merging, total_reintegrate_revisions_that_need_merging)
    write_report_commit_tables(report_file, feature_branch, integration_branch, catch_up_merge_info, total_catchup_revisions_that_need_merging, reintegrate_merge_info, total_reintegrate_revisions_that_need_merging)
    write_report_script(report_file, catch_up_merge_info, total_catchup_revisions_that_need_merging, reintegrate_merge_info, total_reintegrate_revisions_that_need_merging)
    
    write_report_footer(report_file, feature_branch, integration_branch, merge_warning_days_threshold, merge_overdue_days_threshold, merge_warning_commits_threshold, merge_overdue_commits_threshold, repos, total_catchup_revisions_that_need_merging, total_reintegrate_revisions_that_need_merging)

    report_file.close()
    print 'Creating smaller version of report for use in the complete build page..'
    sys.stdout.flush()
    create_static_report_image()

sys.exit(0)