# Lead Qualification Agent

## Portfolio entry

Scores inbound leads against a rubric the client defines, pushes qualified ones into HubSpot with a written summary, and routes the rest to a nurture list so reps only see leads worth their time. The rubric lives in a JSON file rather than the code, so reusing the system for a client with different criteria is a config change instead of a rebuild. Scoring returns structured output, a number, a decision, a specific reason, and a list of anything the lead didn't provide.

**Stack:** Python, LangChain, Pydantic, HubSpot API, Slack

---

## What "qualified" actually means

It means something different at every company, and that's the whole design problem.

A $5,000 minimum budget is right for one client and absurd for another. Company size bands, acceptable timelines, where the threshold sits, all of it is business-specific. Encode one company's version into the agent and the project has to be rebuilt for the next one.

So it's a file:

```json
{
  "min_budget": 5000,
  "good_timelines": ["immediate", "1-3 months"],
  "target_company_sizes": ["11-50", "51-200", "201-1000"],
  "qualify_threshold": 60
}
```

The scoring logic, the reasoning the model does against that rubric, stays identical. Onboarding a new client is a conversation about their numbers, not a sprint.

## Rules alone don't work here

A pure point system misses the thing a human notices instantly. Two leads fill in identical budget and timeline fields. One wrote three specific sentences about their problem. The other wrote "just curious what you guys offer, might be interested someday".

Same score under a rules engine. Completely different prospects.

So the model gets the structured fields and the free text, and it's told not to inflate scores to be nice. In the sample data that's why one lead with every form field completed still scores 22 out of 100.

## Structured output, and why it earns its place

Every score comes back as a typed object: the number, a qualified boolean, a written reason, and a `missing_info` list.

The boolean drives the routing. The reason is for the rep, who trusts a ranking much more when it says "strong budget, immediate timeline, specific need described" than when it just says 88.

## A small integration honesty note

HubSpot's standard contact properties don't include a lead score. Rather than require every client to create custom properties before the integration works at all, the score and reasoning are attached to the contact as a note, and the README explains how to promote them to real filterable properties if a client wants that.

Small thing, but it's the difference between an integration that works on a fresh account and one that 400s on first run.

## The loop that isn't closed

The agent flags when a lead didn't give enough information to judge properly. Nothing acts on that yet. Sending an automatic clarifying question, then re-scoring, is the obvious next step and it isn't built.

Also on the list: a webhook from the client's actual form instead of a CSV, and Salesforce and Airtable, which come up about as often as HubSpot.

## My part

The rubric-as-config approach, the structured scoring pipeline, and the CRM and Slack layer with its local fallback.
