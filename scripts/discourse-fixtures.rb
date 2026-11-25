# frozen_string_literal: true

# Local fixture setup only: run via discourse-agent-check.py prepare.
# Credentials arrive on stdin, never in command arguments or fixture output.
require "json"
input = JSON.parse(STDIN.read)
tag = input.fetch("tag")
raise "Invalid fixture tag" unless tag.match?(/\A[a-z0-9-]{1,32}\z/)

SiteSetting.wizard_enabled = false
SiteSetting.rich_editor = false
SiteSetting.port = "4200"
SiteSetting.title = "WAATA Discourse QA"
SiteSetting.default_locale = "en"
SiteSetting.enable_names = true
SiteSetting.display_name_on_posts = true
SiteSetting.prioritize_username_in_ux = false
SiteSetting.min_trust_to_edit_wiki_post = 1
SiteSetting.rate_limit_create_topic = 0
SiteSetting.rate_limit_create_post = 0
SiteSetting.disable_emails = "non-staff"
SiteSetting.max_logins_per_ip_per_minute = 100

users = {}
%w[admin member].each do |role|
  data = input.fetch(role)
  user = User.find_by(username: "waata_#{role}") || User.new(username: "waata_#{role}")
  user.email = data.fetch("login")
  user.password = data.fetch("password") if user.new_record?
  user.name = role == "member" ? "Member Fixture" : "Admin Fixture"
  user.active = true
  user.approved = true
  user.admin = role == "admin"
  user.trust_level = role == "admin" ? 4 : 1
  user.last_seen_at = Time.zone.now
  user.save!
  user.email_tokens.update_all(confirmed: true)
  user.user_option.update!(enable_quoting: true)
  user.user_option.update!(text_size: "normal") if input.fetch("reset_preferences", true)
  users[role] = user
end
admin, member = users.values_at("admin", "member")
category = Category.find_by(name: "WAATA Lab") || Category.create!(name: "WAATA Lab", color: "0088CC", text_color: "FFFFFF", user: admin)

scenes = {}
def topic_fixture(admin, category, title, body, wiki = false)
  post = PostCreator.create!(admin, title: title, raw: body, category: category.id, skip_validations: true, skip_jobs: true)
  post.update!(wiki: wiki)
  { "topic_id" => post.topic_id, "post_id" => post.id, "title" => title, "body" => body, "url" => "http://127.0.0.1:4200/t/#{post.topic.slug}/#{post.topic_id}" }
end

scenes["DC01"] = {"title" => "WAATA launch checklist #{tag}", "body" => "The local team will review the launch checklist before opening the forum.", "url" => "http://127.0.0.1:4200/c/#{category.slug}/#{category.id}"}
{
  "DC02" => ["WAATA reply practice", "Please review this local discussion fixture."],
  "DC03" => ["WAATA like practice", "Please like this local administrator post once."],
  "DC05" => ["WAATA edit practice", "This topic is used for the member reply editing exercise."],
  "DC06" => ["WAATA bookmark practice", "This topic is used for the bookmark exercise."],
  "DC07" => ["WAATA wiki conversion", "The local wiki conversion fixture must retain this content."],
  "DC09" => ["WAATA shared guide", "The shared test guide is waiting for member review.", true],
  "DC09-control" => ["WAATA ordinary control", "This ordinary administrator post must not be editable by a member."],
  "DC10" => ["WAATA wiki handoff", "The fixture checklist currently describes a draft handoff.", true],
}.each do |id, values|
  scenes[id] = topic_fixture(admin, category, "#{values[0]} #{tag}", values[1], values[2] || false)
end
reply = PostCreator.create!(member, topic_id: scenes["DC05"]["topic_id"], raw: "The test meeting starts on Thursday.", skip_validations: true, skip_jobs: true)
scenes["DC05"]["reply_id"] = reply.id
scenes["DC05"]["post_number"] = reply.post_number
scenes["DC04"] = {"url" => "http://127.0.0.1:4200/u/waata_member/preferences/interface"}
scenes["DC08"] = {"url" => "http://127.0.0.1:4200/u/waata_admin/invited/pending", "description" => "WAATA practice invite #{tag}"}
scenes["DC11"] = {"url" => scenes["DC08"]["url"], "description" => "WAATA scoped invite #{tag}", "keep" => "WAATA keep invite #{tag}"}
%w[description keep].each do |key|
  invite = Invite.generate(admin, description: scenes["DC11"][key], max_redemptions_allowed: 2, skip_email: true)
  scenes["DC11"]["#{key}_id"] = invite.id
end
puts JSON.generate({tag: tag, revision: "3e7317b3344cca6c6510a32cc4c5c0f540132ad9", category_id: category.id, scenes: scenes})
