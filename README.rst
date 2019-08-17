🐍🐍🐍🤖
========

License: Your choice of MIT or Apache License 2.0

This is the code behind trio-bot, a Trio-powered github bot for
helping us maintain the python-trio projects.


Features
========

Right now the main feature is to invite folks to join the org after
their first PR is merged. There are also lots of new features we could
add – for more ideas see:

* https://github.com/python-trio/trio/issues/220
* https://github.com/python-trio/trio/issues/1187

There's also a nice generic library for writing Github Apps hidden in
the ``gh.py`` file – possibly it should get migrated into its own
project at some point.


Repo setup and permissions
==========================

The bot runs on Heroku, and is automatically re-deployed every time a
commit lands in the ``master`` branch.

The production deployment has access to powerful credentials –
basically equivalent to an organization administrator. For example, if
the bot became evil, it could kick us all out and take over the
project for itself. So this repo is a bit more locked down than most
of our repos: the code is public and anyone can submit PRs, but branch
protection is set to that only python-trio admins can actually merge
PRs into master.


What the heck is a "Github App"?
================================

I found the "Github Apps" concept super confusing and it took me a
long time to figure out how it all fits together. I'm going to try to
save you that trouble.

Let's say we want to write a program that does automated actions on
Github – a "bot". Concretely, there are exactly two ways that a bot
interacts with Github:

- They can send requests to the Github API, to ask for information or
  to make changes. This happens whenever the bot wants.

- They can receive webhooks from Github. This lets us get notification
  that something happened that we might want to react to. Otherwise
  we'd have to poll the API constantly to watch for changes, which is
  slow and rude.

This requires two things:

- Whenever we use the API, we need to specify some kind of user
  account, so that Github can check permissions and enforce rate
  limits.

- To receive webhooks, we need to set up a public HTTPS server
  somewhere, and then tell Github which events it should send. Again,
  there are some permissions issues here – Github's not going to let
  me go and subscribe to notifications about everything happening in
  NSA/top-secret-repository.

Now technically, you don't need a "Github App" to do these things. You
can use your regular account to make API calls, or you register a
regular user account for your bot and use that. And if you have
permissions on a repo, you can go into the settings and set up webhook
subscriptions. There are lots of older bots that work this way.

But, that's pretty ad hoc. And every tech company CEO/investor is
deeply envious of the iOS App Store. So Github wanted to make their
own App store, where folks could list their bots, and then users could
come along and start using the bot on their repos with one click (and
maybe a credit card). It's convenient for users, provides a revenue
stream for developers and Github, and increases platform lock-in – a
win-win-win!

But, we're not going to be able to generate all that shareholder value
if every time you set up a bot, you have to manually register a new
user account, send it an invitation to join the repo, keep track of
the credentials, and then separately go in and configure some
webhooks...

Also, Github would rather not have folks running armies of thousands
of individual accounts; that looks an awful lot like what spammers do.
But a popular bot can't just use one account, because then you'll run
into all kinds of problems with rate limits, plus your customers are
probably going to get nervous about giving permissions to an account
that *also* has permissions on all their competitors repos. It's all
very awkward.

So that's why "Github Apps" were invented. Basically, the "App" system
is a special set of APIs that makes it **easy to set up a bot once and
use it on lots of different repos**, and to **manage the permissions
involved in doing this**.

Now you might be thinking: "but I'm just a regular human, not a
venture capitalist. I don't care about App stores and credit cards and
thousands of users; I just want to make a little bot that runs on one
repo and makes my life a little easier". That's cool, imaginary
reader. In fact you sound suspiciously like me when I started reading
about this. And the Github App API can handle our problems too; it's
basically the standard way to make bots in general now. But the API
won't make any sense if you don't understand the background of what
it's trying to do.

Anyway, let's make this more concrete. Setting up an App has two
steps. First, you **create** the App, by going to:

  https://github.com/settings/apps/new

There are a ton of fields to fill out there, but basically you're
giving your bot a name, and then saying what permissions it will need
and what webhooks it will want to subscribe to. Also there's a bunch
of secret-related stuff to let you and Github talk to each other
securely. But what you *aren't* doing here is actually giving your bot
any permissions, or subscribing to any webhooks, on any particular
repos.

That happens in the next step, when you **install** the App. This name
is super confusing, because we're not installing anything anywhere.
When you click the "install" button, what it actually does is:

- Creates a kind of virtual user account, that your app will use when
  its accessing *this particular repo or organization*
- Gives that virtual user account the permissions that you listed
  during the "creation" step *on these repos*
- Sets up the webhooks that you listed during the "creation" step *on
  these repos*

Whenever you see the Github API docs refer to an "installation",
that's basically talking about this virtual user. An App can have
multiple installations; each one gets its own virtual user account,
with its own set of permissions and webhook subscriptions. Each of
"installation" is identified by an opaque string called the
"installation id".

So how do you manage all these virtual accounts? With another virtual
account, of course!

When you "create" an app, Github creates *another* virtual user
account, which we'll call the "app account". There's a special
mechanism for authenticating to the Github API using the app account,
that involves a "JWT" and a private key that you have to generate on
the app configuration screen. Once you've figured that part out, you
can make API requests using the app account, *but* the app account is
super locked-down: basically the only operations its allowed to use
are the ones listed on this page, which are all for managing the
application itself:

    https://developer.github.com/v3/apps/

But! The app account has one *special superpower*: it can take an
"installation id", and `turn it into an authorization token
<https://developer.github.com/v3/apps/#create-a-new-installation-token>`__.
Then you can switch to using *that* token to connect to the Github
API, and that's how you do stuff using the virtual user account that
was created for that installation, and it gets its own rate limits,
and because the permissions for different installations are split up
it's harder for your bot to get tricked into accessing data it wasn't
supposed to.

So to summarize, each Github App has:

- A template specifying what permissions and webhooks it needs
- A bunch of virtual accounts created by applying the template
  permissions/webhooks to a specific set of repos
- A master "app account" that your bot can use to access all those
  virtual accounts

And what if you want to make a simple little private bot just for your
project? Then during the "creation" phase you tick an extra checkbox
that makes it so that only you're allowed "install" the app, and
no-one else can. Everything else is exactly the same.

It's pretty complicated, but fortunately, we can hide most of the
complexity inside a library.

The way I'm approaching it for now, is that you create a ``GithubApp``
object representing the app as a whole. Its ``.app_client`` attribute
is a Github client object that uses the app account; but usually, what
you want to do is use ``.client_for(installation_id)`` to get a client
object that uses the token for that installation id. These clients all
automatically handle token renewal, caching, etc., behind the scenes.
And when a webhook is received, we automatically give the handler an
appropriate client object, so in fact you usually don't have to think
about this stuff at all, just use that client and it'll do the right
thing. See ``gh.py`` for more details.


Why "snekomatic"?
=================

It's kind of an inside joke: the Trio logo (and the bot's avatar) is a
`triskelion <https://en.wikipedia.org/wiki/Triskelion>`__ made of
snakes – a trisnekion – and one of Trio's original taglines was "Async
I/O for Humans and Snake People". I think of the 🐍 as standing for
the friendliness, accessibility, etc. that make Python so welcoming,
and the bot's purpose is to make the project itself more welcoming and
accessible, so it just makes sense. Plus it's fun to say.
