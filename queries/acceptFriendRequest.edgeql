with
    request := assert_single(
        select FriendRequest
        filter .id = <uuid>$request_id
            and .recipient.id = global current_user.id
    ),
    sender := request.sender,
    recipient := request.recipient
insert Friend {
    user1 := sender,
    user2 := recipient
}
unless conflict on ((.user1, .user2))
else (
    select Friend
    filter (.user1 = sender and .user2 = recipient)
        or (.user1 = recipient and .user2 = sender)
);

delete FriendRequest
filter .id = <uuid>$request_id;

