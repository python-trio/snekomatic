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

The production deployment basically has administrator permissions on
the python-trio org. If the bot became evil, it could kick us all out
and take over the project for itself. To reduce the risk of that
happening, this repo is a bit more locked down than most of our repos:
the code is public and anyone can submit PRs, but branch protection is
set so that only python-trio administrators can actually merge PRs
into master.


Hacking on snekomatic
=====================

What the heck is a "Github App" anyway?
---------------------------------------

I found the "Github Apps" concept super confusing and it took me a
long time to figure out how it fit together. So here's an overview to
hopefully save you that trouble.

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


Running the tests
-----------------

The tests are fairly straightforward to run locally, though you do
need a Postgres daemon running. The easiest way is to do something
like:

1. Clone a source tree from github, and ``cd`` into it
2. Create a fresh new virtualenv, and activate it
3. Run: ``pip install -r test-requirements.txt``
4. Install docker (`Windows
   <https://docs.docker.com/docker-for-windows/install/>`__, `macOS
   <https://docs.docker.com/docker-for-mac/install/>`__, and I'll
   assume if you're running Linux on your desktop you can figure out
   how to install docker on your distro)
5. Open a new terminal, and run: ``docker run --rm -p 5432:5432
   postgres:alpine``

   This will download and start a temporary Postgres daemon inside a
   container, configured the way we need it. When you're done running
   tests, you can hit control-C again to shutdown and delete the
   container.
6. Back in you first terminal, run: ``pytest``

Note that there are a few tests that contact that Github API directly.
The necessary credentials are baked into the testsuite so it should
just work, but these tests will fail if you're not connected to the
internet.


Testing against Github for real
-------------------------------

The Github credentials we use in the automated test suite are public,
so they're set up to have basically no permissions at all; we only use
them to check we can send requests to Github and parse responses. We
also have automated tests for our more complex code paths (like
inviting people to join the organization!), but they use a fake
version of the Github API that just returns canned responses.

That's great for automated tests to make sure we haven't broken stuff,
but when you're developing a new feature you probably want to
experiment with running it against Github for real! It's the only way
to see what Github actually does.

This is totally doable, but unfortunately it's kind of annoying to set
up. Luckily, you only have to do it once. And we can use Heroku's free
tier, so it won't cost you any money.

**Getting started**

Fork this repo into your personal Github account, and make a branch to
start working on. (Suggestion: for your first change, just add a
``print`` statement at the top of ``snekomatic.app.main``, so when you
look at the program output later you'll be able to confirm that you
really are running your branch.) Push your branch to your new Github
fork.

**Get the code running in the cloud**

Sign up for an account at `Heroku <https://heroku.com>`__.

Click on "Create new app", and give your app a name. Maybe
``<yourname>-snekomatic-test-app``

Click on the "Deploy" tab, and scroll down and connect your new Heroku
app to your Github fork.

Scroll down a little more to the "Automatic deploys" section, then
select your working branch and click "Enable automatic deploys". Now
every time you push to your work-in-progress branch to Github, Heroku
will automatically start running your code on a free cloud VM,
accessible as ``https://<the name you chose for your
app>.herokuapp.com``. If you visit that URL now in your web browser,
you should see a short message from snekomatic.

Switch to the "Resources" tab, and scroll down to where it says
"Add-ons". Use the search box to add a "Heroku Postgres" add-on (free
level).

Then go back to the Add-ons search box, and add "Papertrail", again at
the free tier. Once you've done that, your Add-ons list should have an
entry labeled "Papertrail", which is a link. Click on the link, and
you'll get a live view of logs from your app, in your web browser. I'd
recommend taking a few minutes to look this over and familiarize
yourself with it. You should see the `print` call that you added
above – do you?

Congratulations! You've got a private snekomatic install running in
the cloud, for free. Now we need to hook it up to Github.

**Creating a Github App for testing**

Snekomatic is designed to manage a Github organization, so the easiest
way to test it is to make your own Github organization. Go to
`Github's page for creating a new organization
<https://github.com/organizations/new>`__, and make a new organization
named something like ``<yourname>-test-org``.

Once you've got an org, click on the "Settings" tab, then in the box
on the left you're looking for "Developer Settings → GitHub Apps".
(Note: you *don't* want "Installed GitHub Apps" – that's something
else!) Then on the right side of your screen there should be a button
labeled "New GitHub App". Click on the button.

Then GitHub will give you a huge form to fill out. You can skip a lot
of it, but some parts are important:

*GitHub App name*: Make up a name for your app. It can't match the
name of any existing GitHub account or org, but it doesn't really
matter beyond that. If your bot posts comments, then this is the name
that will appear next to them. I'd suggest using the same name you
used for your app on Heroku.

*Webhook URL*: This has to be: ``https://<your heroku app
name>.herokuapp.com/webhook/github``

*Webhook secret*: This is a secret password that your bot and GitHub
need to agree on. The easiest thing to do is to open up a Python
interpreter, and run ``import secrets; secrets.token_urlsafe()``. Then
paste the blob of data you get into the form, and also save it for
later.

*Permissions*: This control what your app will be able to read/write
on Github. There are separate sections for "Repository permissions",
"Organization permissions", and "User permissions". Currently the
permissions snekomatic needs are:

* Under "Repository permissions": "Pull requests: Read & Write".
* Under "Organization permissions": "Organization members: Read & Write".
* Under "User permissions": None, you can skip this section entirely.

You can give your app more permissions if you want; they'll only be to
your test org, so it's not particularly dangerous, and can be useful
for testing. Also, you can always edit the permissions list again
later if you want to change things.

*Subscribe to events*: This selects which events GitHub will notify
your bot about. Currently snekomatic just needs "Pull requests".
Again, you can always change this in the future.

*Where can this GitHub App be installed?*: choose "Only on this account".

When you're done, click "Create GitHub App". You should see a
configuration page for your new GitHub App. At the top it will say
"About", and then give the app name and an "App ID" (an integer, like
38822 or something). Write down that App ID for later.

Then, you have to create a private key. (This is similar to the
"Webhook secret" you made earlier, but different: the "webhook secret"
is how you can tell that webhook notifications are really coming from
github; the "Private key" is how github can tell that your API
requests are really coming from you.) To do this, you have to scroll
down to the bottom of the "General" configuration page for your new
Github app, and click on the button that says "Generate a private
key". This will prompt you to download a file named
``somethingsomething.private-key.pem``. Save that file somewhere for
later.

Finally, we need to tell Github that we want to actually *use* the
app, by "installing" it on our organization. Until we do this, it
won't actually do anything. On the left side of the app configuration
pages, there should be a box with several options, and one of them is
"Install App". Click on that, and then click to install it on your
organization. When it asks, tell it to install on "All repositories".
OK! The Github install part is finally done.

(In case you lost the app configuration page, you can find it by going
to your Github org → Settings → Developer Settings / Github Apps →
then clicking "Edit" next to your app. You'll probably reference this
page a lot, so you might want to bookmark it or something.)

Now, last step: we need to go back to Heroku, and finish configuring
our app, so that it knows how to connect to the Github stuff we just
set up. Log into Heroku and open up your app. Click on the "Settings"
tab, and find the "Config Vars" section. Click on "Reveal config
vars", and then add the following config vars:

* ``GITHUB_APP_ID``: The integer your wrote down earlier, from the top
  of the Github App configuration page.
* ``GITHUB_WEBHOOK_SECRET``: The "webhook secret" you set earlier.
* ``GITHUB_PRIVATE_KEY``: Open up that ``blahblah.private-key.pem``
  file you saved earlier, and paste its full contents into the text
  field. It should be a bunch of lines, starting with ``-----BEGIN
  RSA PRIVATE KEY-----``.
* ``GITHUB_USER_AGENT``: Your Github username. (`Github says
  <https://developer.github.com/v3/#user-agent-required>`__ that you
  have to set a user-agent whenever connecting to the Github API, and
  gives a few suggestions for what it might look like; this is the
  simplest.)

**Finishing up**

Do stuff on the repo and watch the webhooks get delivered in your logs!

Sorry, that was a lot. If you have any suggestions for how to simplify
it, please let us know. But the good news is, now you know most of
what you need to to set up your own Github apps on your own projects,
since it's pretty much the same process!

**Other tips:**

- Re-delivering webhooks

- The `Heroku CLI
  <https://devcenter.heroku.com/articles/heroku-cli>`__ is very handy.
  You can do things like see logs, change config variables, connect
  directly to your database to poke around, etc.

  Setting up a git remote so it can find your app

- `Sentry <https://sentry.io/>`__ is also handy, because it lets you
  get more info on crashes that happen in your app. You should be able
  to add the free tier as an "Add-on" in Heroku, and snekomatic will
  automatically start delivering crash reports.


Why is it called "snekomatic"?
==============================

It's kind of an inside joke: the Trio logo (and the bot's avatar) is a
`triskelion <https://en.wikipedia.org/wiki/Triskelion>`__ made of
snakes – a trisnekion – and one of Trio's original taglines was "Async
I/O for Humans and Snake People". I think of the 🐍 as standing for
the friendliness, accessibility, etc. that make Python so welcoming,
and the bot's purpose is to make the project itself more welcoming and
accessible, so it just makes sense. Plus it's fun to say.
