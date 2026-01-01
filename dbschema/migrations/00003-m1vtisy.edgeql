CREATE MIGRATION m1vtisyimxhdhd2vnavathbzofihze4na6xdaqnymyytqlsafxqt5a
    ONTO m1eklprw7x66mxihzhslmvuzlmfwd2kvedokqqn4drp3u6xm7e6byq
{
  ALTER TYPE default::User {
      ALTER PROPERTY username {
          CREATE CONSTRAINT std::exclusive;
      };
  };
};
