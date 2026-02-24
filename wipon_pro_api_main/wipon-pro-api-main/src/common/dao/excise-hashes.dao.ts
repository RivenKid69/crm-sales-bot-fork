import { Column, Entity, PrimaryGeneratedColumn } from 'typeorm';

@Entity('excise-hashs')
export class ExciseHashesDao {
  @PrimaryGeneratedColumn()
  id: number;

  @Column()
  hash: string;

  @Column({ name: 'saved_at' })
  saved_at: Date;
}
