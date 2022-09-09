# ninja-points

This repo helps us calculate point values from contributions from our various communication channels.

## GitHub contributions

For contributions to GitHub, we use search filters to find people's contributions. You can run these from [github.com/pulls](https://github.com/pulls)

### Bugfix Pull Request

For example, to find all eligible bugfix pull requests:

```
is:merged is:pr archived:false user:redhat-cop author:etsauer updated:>=2017-03-01 -label:enhancement
```

### Enhancement Pull Request

```
is:merged is:pr archived:false user:redhat-cop label:enhancement author:etsauer updated:>=2017-03-01
```

### Reviewed pull requests

```
is:merged is:pr archived:false user:redhat-cop reviewed-by:etsauer updated:>=2017-03-01
```

### Closed Issues

```
is:closed is:issue archived:false user:redhat-cop assignee:etsauer updated:>=2017-03-01
```

### Script

A script called [github-stats.py](github-stats.py) is available to automate the aggregation of statistics from the [redhat-cop GitHub organization](https://github.com/redhat-cop).

To be able to query the GitHub API, create a new [Personal Access Token](https://github.com/settings/tokens). Configure a key with at least read access.

Then configure the `GITHUB_API_TOKEN` environment variable as follows:

```
export GITHUB_API_TOKEN='<API_KEY>'
```

Execute the script:

```
$ ./github-stats.py

=== Statistics for GitHub Organization 'redhat-cop' ====

== General PR's ==

enhancement:
  csmith - 1
    ninja-points - Enhancement to GitHub script
```

By default, the script uses a search range from March 1 of a calendar year to the present. To specify an alternate date, use the `--start-date` argument such as `--start-date=2017-09-01`.

To limit to a specific user, the `--username` parameter can be specified.

To filter by labels, the `--labels` parameter can be specified followed by a series of comma separated labels. To limit the results containing a label, add a `-` at the end of the label name, such as `bugfix-` Note: Positive and negative logic cannot be combined.


## Trello

### Cards Completed By Member worth 2 points

```
list:Done member:andrewblock edited:365 name:"\(2\)"
```

### Script

A script called [trello-stats.py](trello-stats.py) is available to automate the aggregation of statistics of cards within an organization

First, get an API key [here](https://trello.com/app-key)

Then, configure the following variables:

```
export TRELLO_API_KEY='<API_KEY>'
export TRELLO_API_TOKEN='<API_TOKEN>'
```

Execute the script:

```
$ ./trello-stats.py
=== Statistics for Trello Team 'Red Hat CoP' ====

csmith has 2 cards
   - Board: RHEL Platform | Card: Document SELinux Booleans
   - Board: OpenShift Container Platform | Card: Add input field to product page

jdoe has 1 cards
   - Board: OpenShift Container Platform | Card: E2E Test Enhancements
```

By default, the script uses a search range from March 1 of a calendar year to the present. To specify an alternate date, use the `--start-date` argument such as `--start-date=2017-09-01`.

To limit to a specific user, the `--username` parameter can be specified.

Additional queries can be generated by referencing the following:

http://help.trello.com/article/808-searching-for-cards-all-boards

## GitLab

### Script

A script called [gitlab-stats.py](gitlab-stats.py) contributions made within within an organization.

To be able to query the GitLab API, create a new [Personal Access Token](https://docs.gitlab.com/ee/user/profile/personal_access_tokens.html).

Then configure the `GITLAB_API_TOKEN` environment variable as follows:

```
export GITLAB_API_TOKEN='<API_KEY>'
```

Execute the script:

```
$ ./gitlab-stats.py

=== Statistics for GitLab Group 'redhat-cop' ====

== Merged MR's ==

dhowe - 1
  ninja-points - Minor change to GitLab script
```

## RocketChat

### Script

A script called [rocketchat.py](rocketchat.py) is available to automate statistics from [RocketChat](https://rocket.chat/).

Configure the following variables:

```
export ROCKETCHAT_USERNAME='<ROCKETCHAT_USERNAME>'
export ROCKETCHAT_PASSWORD='<ROCKETCHAT_PASSWORD>'
```

Execute the script:

```
$ ./rocketchat.py -d 2 -f "#cop-channel" 
=== Rocketchat Statistics For 03/27/2018 - 03/29/2018 ===

#emerging-tech
  2 Users Joined
  0 Users Removed
  14 Messages
    * jdoe - 64.29% - 9 Messages
    * mmurray - 28.57% - 4 Messages
    * csmart - 7.14% - 1 Message
#dev-ops
  8 Users Joined
  1 Users Removed
  10 Messages
    * jdoe - 40.00% - 4 Messages
    * mmurray - 30.00% - 3 Messages
    * csmart - 20.00% - 2 Messages
    * ashore - 10.00% - 1 Message
```

The script queries channels with a particular description as specified by the `-f` parameter and the number of days to search in the past using the `-d` parameter.

## Google Hangouts Chat

### Script

A script called [hangouts-chat.py](hangouts-chat.py) is available to automate statistics from [Google Hangouts Chat](https://chat.google.com).

A service account token file is used to authenticate to the Google. Configure the following variable specifying the location of this file:

```
export SERVICE_ACCOUNT_KEY_FILE='<SERVICE_ACCOUNT_KEY_FILE>'
```

Execute the script:

```
$ ./hangouts-chat.py
=== Statistics for Google Hangouts Chat

- containers - 55 Members
- openshift-development - 311 Members
```

## Mailman

### Script

A script called [mailman-subscribers.py](mailman-subscribers.py) is available to collect statistics based on mailing list subscriptions.

Execute the script:

```
$ ./mailman-subscribers [ options ] hostname listname password

ashore@redhat.com
csmart@redhat.com
mmurray@redhat.com
```
