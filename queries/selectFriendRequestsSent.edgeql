select FriendRequest {
    id,
    recipient: {
        id,
        username,
        avatar
    },
    created_at
}
filter .sender.id = global current_user.id
order by .created_at desc;


