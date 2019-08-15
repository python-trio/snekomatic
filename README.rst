🐍🐍🐍
=====

License: Your choice of MIT or Apache License 2.0


What the heck is a "Github App"?
================================

I found "Github Apps" super confusing and it took me a long time to
figure out how it all fits together, so I'm going to try to save you
that trouble.

So. Let's say we want to write a program that does automated actions
on Github – a "bot". Concretely, there are exactly two ways that a bot
interacts with Github:

- They can send requests to the Github API, to ask for information or
  to make changes. This is totally driven by us.

- They can receive webhooks from Github. This lets us get notification
  that something happened that we might want to react to. Otherwise
  we'd have to poll the API constantly to watch for changes, which is
  slow and rude. Often, after we get a notification, we'll respond by
  making some new Github API calls, but really we could do anything.

To do this, we need two things:

- To use the API, our bot will need some kind of user account, so that
  Github can check permissions, and enforce rate limits.

- To receive webhooks, we need to set up a public HTTPS server
  somewhere, and then tell Github which events it should send. Again,
  there are some permissions issues here – I can't go subscribing to
  notifications about some other company's private repository.

Now technically, you don't need a "Github App" to do these two things.
You can use your regular account to make API calls, or go to the
regular Github "signup" page and register a dedicated user account for
your bot. And if you have permissions on a repo, you can go into the
settings and set up webhook subscriptions. There are lots of older
bots that work this way.

But, that's pretty ad hoc. And every tech company CEO/investor is
deeply envious of the iOS App Store. So Github wanted to make their
own App store, where folks could list their bots, and then users could
come along and start using the bot on their repos with one click (and
maybe a small credit card payment). But that's not going to work if
every time you set up a bot, you have to manually register a new user
account, send it an invitation to join the repo, keep track of the
credentials, and then separately go in and configure some webhooks...

Also, Github would rather not have folks running armies of thousands
of individual accounts; that looks an awful lot like what spammers do.
But a popular bot can't just use one account, because then you'll run
into all kinds of problems with rate limits, plus your customers are
probably going to get nervous about giving permissions to an account
that *also* has permissions on all their competitors repos.

So that's why "Github Apps" were invented. Basically, the "App" system
is a special set of APIs that makes it **easy to set up a bot once and
use it on lots of different repos**, and to **manage the necessary
permissions**.

Now you might be thinking: "but I'm just a regular human, not a
venture capitalist. I don't care about App stores and credit cards and
thousands of users; I just want to make a little bot that runs on one
repo and makes my life a little easier". That's cool, imaginary
reader. In fact you sound suspiciously like me when I started studying
this. And the Github App API can handle that case too; they're
basically the standard way to make bots in general now. But the API
won't make any sense if you don't understand the background of what
it's trying to do.

Anyway, let's make this more concrete. Setting up an App has two
steps. First, you **create** the App, by going to:

  https://github.com/settings/apps/new

There are a ton of fields to fill out there, but basically the point
is to give your bot a name, and say what permissions it will need and
what webhooks it will want to subscribe to. Also there's a bunch of
secret-related stuff to let you and Github talk to each other
securely. But what you *aren't* doing here is actually giving your bot
any permissions, or subscribing to any webhooks.

That happens in the next step, when you **install** the App. This name
is super confusing, because nothing is getting installed anywhere.
When you click the "install" button, what it actually does is:

- Creates a kind of virtual user account, that your app will use when
  its accessing this particular repo or organization
- Gives that virtual user account the permissions that you listed
  during the "creation" step, on the relevant repos
- Sets up the webhooks that you listed during the "creation" step, on
  the relevant repos

Whenever you see the Github API docs refer to an "installation",
that's basically talking about this virtual user that was created
here. An App can have multiple installations; each one gets its own
virtual user account, and each has its own set of permissions and
webhooks.
