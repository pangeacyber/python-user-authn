# Authenticating Users for Access Control with RAG in Python

An example Python app demonstrating how to integrate Pangea's [AuthN][] and
[AuthZ][] services to filter out RAG documents based on user permissions.

## Prerequisites

- Python v3.12 or greater.
- pip v24.2 or [uv][] v0.4.29.
- A [Pangea account][Pangea signup] with AuthN and AuthZ enabled.
- An [OpenAI API key][OpenAI API keys].

## Setup

### Pangea AuthN

After activating AuthN, under AuthN > General > Redirect (Callback) Settings,
add `http://localhost:3000` as a redirect and save.

Under AuthN > Users > New > Create User, create at least one user.

### Pangea AuthZ

The setup in AuthZ should look something like this:

#### Resource types

| Name        | Permissions |
| ----------- | ----------- |
| engineering | read        |
| finance     | read        |

#### Roles & access

> [!TIP]
> At this point you need to create 2 new Roles under the `Roles & Access` tab in
> the Pangea console named `engineering` and `finance`.

##### Role: engineering

| Resource type | Permissions (read) |
| ------------- | ------------------ |
| engineering   | ✔️                 |
| finance       | ❌                 |

##### Role: finance

| Resource type | Permissions (read) |
| ------------- | ------------------ |
| engineering   | ❌                 |
| finance       | ✔️                 |

#### Assigned roles & relations

| Subject type | Subject ID          | Role/Relation |
| ------------ | ------------------- | ------------- |
| user         | your AuthN username | engineering   |
| user         | bob@example.org     | finance       |

_Note:_ Change or add assigned roles for your user to change permissions and access over time.

### Repository

```shell
git clone https://github.com/pangeacyber/python-user-authn.git
cd python-user-authn
```

If using pip:

```shell
python -m venv .venv
source .venv/bin/activate
pip install .
```

Or, if using uv:

```shell
uv sync
source .venv/bin/activate
```

The sample can then be executed with:

```shell
python -m user_authn --user alice "What is the software architecture of the company?"
```

## Usage

```
Usage: python -m user_authn [OPTIONS] PROMPT

Options:
  --authn-client-token TEXT  Pangea AuthN Client API token. May also be set
                             via the `PANGEA_AUTHN_CLIENT_TOKEN` environment
                             variable.  [required]
  --authn-hosted-login TEXT  Pangea AuthN Hosted Login URL. May also be set
                             via the `PANGEA_AUTHN_HOSTED_LOGIN` environment
                             variable.  [required]
  --authz-token SECRET       Pangea AuthZ API token. May also be set via the
                             `PANGEA_AUTHZ_TOKEN` environment variable.
                             [required]
  --pangea-domain TEXT       Pangea API domain. May also be set via the
                             `PANGEA_DOMAIN` environment variable.  [default:
                             aws.us.pangea.cloud; required]
  --model TEXT               OpenAI model.  [default: gpt-4o-mini; required]
  --openai-api-key SECRET    OpenAI API key. May also be set via the
                             `OPENAI_API_KEY` environment variable.
                             [required]
  --help                     Show this message and exit.
```

Let's assume the current user is "alice@example.org" and that they should have
permission to see engineering documents. They can query the LLM on information
regarding those documents:

```shell
$ python -m user_authn --user alice "What is the software architecture of the company?"
```

This will open a new tab in the user's default web browser where they can login
through AuthN. Afterwards, their permissions are checked against AuthZ and they
will indeed receive a response that is derived from the engineering documents:

```
The company's software architecture includes a frontend developed using
React.js, Redux, Axios, and Material-UI, while the backend is built with Node.js
and Express.js. MongoDB is used for the database, and authentication and
authorization are handled through JSON Web Tokens (JWT) and OAuth 2.0. Version
control is managed using Git and GitHub.
```

But they cannot query finance information:

```shell
$ python -m user_authn --user alice "What is the top salary in the Engineering department?"

# [login flow]

I don't know the answer, and you may not be authorized to know it.
```

And vice versa for "bob@example.org", who is in finance but not engineering.

[AuthN]: https://pangea.cloud/docs/authn/
[AuthZ]: https://pangea.cloud/docs/authz/
[Pangea signup]: https://pangea.cloud/signup
[OpenAI API keys]: https://platform.openai.com/api-keys
[uv]: https://docs.astral.sh/uv/
