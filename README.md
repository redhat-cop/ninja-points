# ninja-points

This repo helps us calculate point values from contributions to our github and trello spaces.

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

## Trello

Still figuring it out, but this might help some.

http://help.trello.com/article/808-searching-for-cards-all-boards
