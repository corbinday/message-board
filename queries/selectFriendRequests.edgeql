select FriendRequest {
    id,
    sender: {
        id,
        username,
        avatar
    },
    created_at
}
filter .recipient.id = global current_user.id
order by .created_at desc;


