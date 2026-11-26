# frozen_string_literal: true

# Independent read-only persisted-state audit. Never return invite URLs/tokens.
require "json"
fixture = JSON.parse(STDIN.read)
member = User.find_by!(username: "waata_member")
admin = User.find_by!(username: "waata_admin")
results = {}
scenes = fixture.fetch("scenes")
scenes.each do |key, scene|
  next if key == "DC09-control"
  result = case key
  when "DC01"
    topics = Topic.where(title: scene.fetch("title"))
    {count: topics.count, body: topics.first&.first_post&.raw, category: topics.first&.category&.name}
  when "DC02"
    {replies: Post.where(topic_id: scene.fetch("topic_id")).where("post_number > 1").map { |p| {body: p.raw, username: p.user.username, name: p.user.name} }}
  when "DC03"
    {liked: PostAction.where(post_id: scene.fetch("post_id"), user_id: member.id, post_action_type_id: PostActionType.types[:like], deleted_at: nil).exists?}
  when "DC04"
    {text_size: member.user_option.reload.text_size}
  when "DC05"
    reply = Post.find(scene.fetch("reply_id"))
    {post_id: reply.id, post_number: reply.post_number, body: reply.raw, username: reply.user.username}
  when "DC06"
    bookmarks = Bookmark.where(user_id: member.id).where(
      "(bookmarkable_type = 'Post' AND bookmarkable_id = ?) OR (bookmarkable_type = 'Topic' AND bookmarkable_id = ?)",
      scene.fetch("post_id"), scene.fetch("topic_id")
    )
    {bookmarked: bookmarks.exists?, bookmarks: bookmarks.map { |b| {type: b.bookmarkable_type, reminder_at: b.reminder_at} }}
  when "DC07", "DC09", "DC10"
    post = Post.find(scene.fetch("post_id"))
    data = {body: post.raw, wiki: post.wiki}
    if key == "DC09"
      control = Post.find(scenes.fetch("DC09-control").fetch("post_id"))
      data[:control_can_edit] = Guardian.new(member).can_edit?(control)
      data[:wiki_can_edit] = Guardian.new(member).can_edit?(post)
    end
    data
  when "DC08", "DC11"
    descriptions = key == "DC08" ? [scene.fetch("description")] : [scene.fetch("description"), scene.fetch("keep")]
    {invitations: descriptions.to_h { |description|
      rows = Invite.where(invited_by_id: admin.id, description: description, deleted_at: nil)
      [description, rows.map { |i| {id: i.id, redeemed: i.redemption_count, max_uses: i.max_redemptions_allowed, expires_at: i.expires_at, future_expiry: i.expires_at > Time.zone.now, email_absent: i.email.blank?} }]
    }}
  end
  results[key] = result
end
puts JSON.generate({read_only: true, target_database: "Discourse container only", results: results})
