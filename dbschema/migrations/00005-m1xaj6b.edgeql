CREATE MIGRATION m1xaj6bljuymkinojpxtylvozyxwyswknpdsf52ztmsxdmtwo2ei6a
    ONTO m1mm67jkrk5gvvtrjzqhmup2ilspnfm4s6vmeoed7x5nexlxxk3tmq
{
  CREATE TYPE default::Message {
      CREATE LINK recipient: default::User;
      CREATE LINK sender: default::User;
      CREATE REQUIRED PROPERTY created_at: std::datetime {
          CREATE REWRITE
              INSERT 
              USING (std::datetime_of_statement());
      };
      CREATE PROPERTY payload: std::bytes;
  };
};
