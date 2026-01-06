with
    current_user_id := global current_user.id
select User {
    id,
    username,
    avatar
}
filter .username ilike '%' ++ <str>$username ++ '%'
    and .id != current_user_id
    and not exists (
        select Friend
        filter (
            (.user1.id = current_user_id and .user2.id = .id)
            or (.user2.id = current_user_id and .user1.id = .id)
        )
    )
    and not exists (
        select FriendRequest
        filter (
            (.sender.id = current_user_id and .recipient.id = .id)
            or (.recipient.id = current_user_id and .sender.id = .id)
        )
    )
order by .username
limit 10;

