CREATE MIGRATION m1otceflqvxjslq6xb2dnssim7y3djkyxjiwl2pddqoizt5rqnf6oq
    ONTO m1tnfl5o2j5x53rsmwdul4zy342qfdl34jvnqruu2ioqd344ni4nra
{
  ALTER GLOBAL default::current_user USING (std::assert_single((SELECT
      default::User
  FILTER
      (GLOBAL ext::auth::ClientTokenIdentity IN .identity)
  )));
};
