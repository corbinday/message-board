insert FriendRequest {
    sender := global current_user,
    recipient := assert_single(
        select User
        filter .id = <uuid>$recipient_id
    )
}
unless conflict on ((.sender, .recipient))
else (
    select FriendRequest
    filter .sender = global current_user
        and .recipient.id = <uuid>$recipient_id
);


