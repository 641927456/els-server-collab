from qa_environment import F,R,B
import els_server.domain,els_server.storage
els_server.domain.__path__.insert(0,str(F/'source-v2/els_server/domain'))
els_server.storage.__path__.insert(0,str(F/'source-v2/els_server/storage'))
